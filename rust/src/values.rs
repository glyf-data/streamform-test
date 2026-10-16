//! Comparing a value a test wrote with a value the binary reported.
//!
//! The binary renders values after typing them against the model's output
//! schema: decimals as exact strings (`"28"`), timestamps as RFC 3339 with
//! milliseconds (`"2026-08-30T10:00:00.000Z"`), integers and booleans as
//! themselves. A test writes `28`, `28.0`, or `"2026-08-30T10:00:00Z"`. These
//! rules make the two compare equal when they mean the same value.

use serde_json::{Map, Value};

/// A plain decimal literal in canonical form: no sign on zero, no leading
/// zeros, no trailing fractional zeros. `None` for anything else, exponents included.
fn decimal(text: &str) -> Option<String> {
    let (negative, digits) = match text.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, text.strip_prefix('+').unwrap_or(text)),
    };
    let (whole, fraction) = digits.split_once('.').unwrap_or((digits, ""));
    if whole.is_empty() && fraction.is_empty()
        || !whole.bytes().all(|b| b.is_ascii_digit())
        || !fraction.bytes().all(|b| b.is_ascii_digit())
    {
        return None;
    }
    let whole = whole.trim_start_matches('0');
    let fraction = fraction.trim_end_matches('0');
    let whole = if whole.is_empty() { "0" } else { whole };
    let body = if fraction.is_empty() {
        whole.to_string()
    } else {
        format!("{whole}.{fraction}")
    };
    Some(if negative && body != "0" {
        format!("-{body}")
    } else {
        body
    })
}

fn as_decimal(value: &Value) -> Option<String> {
    match value {
        Value::Number(n) => decimal(&n.to_string()),
        Value::String(s) => decimal(s),
        _ => None,
    }
}

/// An RFC 3339 instant in UTC (`Z`) with its fractional zeros trimmed.
fn as_instant(value: &Value) -> Option<String> {
    let text = value.as_str()?;
    let body = text.strip_suffix('Z')?;
    if !body.contains('T') {
        return None;
    }
    Some(match body.split_once('.') {
        Some((seconds, fraction)) => {
            let fraction = fraction.trim_end_matches('0');
            if fraction.is_empty() {
                seconds.to_string()
            } else {
                format!("{seconds}.{fraction}")
            }
        }
        None => body.to_string(),
    })
}

/// Whether `expected`, as a test wrote it, means the value `actual` the binary reported.
pub fn same(expected: &Value, actual: &Value) -> bool {
    match (expected, actual) {
        (Value::Null, _) | (_, Value::Null) => expected.is_null() && actual.is_null(),
        (Value::Bool(_), _) | (_, Value::Bool(_)) => expected == actual,
        _ => {
            if let (Some(a), Some(b)) = (as_decimal(expected), as_decimal(actual)) {
                return a == b;
            }
            if let (Some(a), Some(b)) = (as_instant(expected), as_instant(actual)) {
                return a == b;
            }
            expected == actual
        }
    }
}

/// Whether the rows name the same columns with the same values.
pub fn same_row(expected: &Map<String, Value>, actual: &Map<String, Value>) -> bool {
    expected.len() == actual.len()
        && expected
            .iter()
            .all(|(name, value)| actual.get(name).is_some_and(|a| same(value, a)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn numbers_compare_by_value() {
        assert!(same(&json!(28), &json!("28")));
        assert!(same(&json!(13.0), &json!("13")));
        assert!(same(&json!("010.50"), &json!(10.5)));
        assert!(same(&json!(-0), &json!("0")));
        assert!(!same(&json!(27), &json!("28")));
    }

    #[test]
    fn instants_compare_by_value_and_strings_by_text() {
        assert!(same(
            &json!("2026-08-30T10:00:00Z"),
            &json!("2026-08-30T10:00:00.000Z")
        ));
        assert!(!same(
            &json!("2026-08-30T10:00:00Z"),
            &json!("2026-08-30T10:00:01Z")
        ));
        assert!(same(&json!("abc"), &json!("abc")));
        assert!(!same(&json!(true), &json!("true")));
        assert!(same(&Value::Null, &Value::Null));
    }
}
