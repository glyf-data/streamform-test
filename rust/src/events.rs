//! Building event streams: time stepping, files, and merging by event time.
//!
//! Loops are Rust's own iterators (`(0..1000).map(|i| json!({...}))`); this
//! module adds what needs event time:
//!
//! ```no_run
//! use serde_json::json;
//! use streamform_test::events::{self, Item};
//!
//! let orders = events::timed((0..6).map(|_| json!({"customer_id": 42, "amount": 10})),
//!                            "ordered_at", "2026-08-30T10:00:00Z", "1m");
//! let refunds = events::read_jsonl("refunds.jsonl").unwrap();
//! let stream: Vec<Item> = events::with_watermarks(
//!     events::merge(vec![orders, refunds], "ordered_at"), "ordered_at", "1m");
//! ```

use std::path::Path;

use serde_json::{Map, Value};

/// One item of a stream: an event, or the source's watermark advanced to an RFC 3339 instant.
#[derive(Debug, Clone, PartialEq)]
pub enum Item {
    /// An event: a JSON object of column values.
    Event(Value),
    /// The watermark advanced to this instant.
    Watermark(String),
}

/// `"500ms"`, `"30s"`, `"5m"`, `"2h"` or `"7d"` in milliseconds.
pub fn duration_ms(text: &str) -> i64 {
    let text = text.trim();
    let split = text
        .find(|c: char| !c.is_ascii_digit())
        .unwrap_or_else(|| panic!("not a duration: {text:?}; write it like 500ms, 30s or 5m"));
    let (number, unit) = text.split_at(split);
    let n: i64 = number
        .parse()
        .unwrap_or_else(|_| panic!("not a duration: {text:?}"));
    n * match unit {
        "ms" => 1,
        "s" => 1_000,
        "m" => 60_000,
        "h" => 3_600_000,
        "d" => 86_400_000,
        _ => panic!("not a duration: {text:?}; write it like 500ms, 30s or 5m"),
    }
}

// Days from 1970-01-01 to a civil date, and back (Howard Hinnant's algorithms).
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (
        if m <= 2 {
            yoe + era * 400 + 1
        } else {
            yoe + era * 400
        },
        m,
        d,
    )
}

/// An RFC 3339 instant in UTC (`2026-08-30T10:00:00Z`, optionally with a fraction) in epoch milliseconds.
pub fn instant_ms(text: &str) -> i64 {
    fn fail(text: &str) -> ! {
        panic!("not an RFC 3339 instant in UTC: {text:?}")
    }
    let body = text.strip_suffix('Z').unwrap_or_else(|| fail(text));
    let (date, time) = body.split_once('T').unwrap_or_else(|| fail(text));
    let num = |s: &str| s.parse::<i64>().unwrap_or_else(|_| fail(text));
    let d: Vec<i64> = date.split('-').map(num).collect();
    let (clock, fraction) = time.split_once('.').unwrap_or((time, ""));
    let t: Vec<i64> = clock.split(':').map(num).collect();
    if d.len() != 3 || t.len() != 3 {
        fail(text);
    }
    let millis = format!("{fraction:0<3}")[..3]
        .parse::<i64>()
        .unwrap_or_else(|_| fail(text));
    (days_from_civil(d[0], d[1], d[2]) * 86_400 + t[0] * 3_600 + t[1] * 60 + t[2]) * 1_000 + millis
}

/// Epoch milliseconds as the RFC 3339 text fixtures use.
pub fn rfc3339(ms: i64) -> String {
    let (days, rest) = (ms.div_euclid(86_400_000), ms.rem_euclid(86_400_000));
    let (y, m, d) = civil_from_days(days);
    let (h, min, s, frac) = (
        rest / 3_600_000,
        rest / 60_000 % 60,
        rest / 1_000 % 60,
        rest % 1_000,
    );
    let mut text = format!("{y:04}-{m:02}-{d:02}T{h:02}:{min:02}:{s:02}");
    if frac != 0 {
        text.push_str(&format!(".{frac:03}"));
    }
    text + "Z"
}

/// The rows with `column` set to `start`, `start + every`, `start + 2 * every`, and so on.
pub fn timed(
    rows: impl IntoIterator<Item = Value>,
    column: &str,
    start: &str,
    every: &str,
) -> Vec<Value> {
    let (first, step) = (instant_ms(start), duration_ms(every));
    rows.into_iter()
        .enumerate()
        .map(|(i, mut row)| {
            row.as_object_mut()
                .expect("an event is a JSON object")
                .insert(
                    column.into(),
                    Value::String(rfc3339(first + i as i64 * step)),
                );
            row
        })
        .collect()
}

fn time_of(row: &Value, by: &str) -> i64 {
    let text = row[by]
        .as_str()
        .unwrap_or_else(|| panic!("event has no `{by}` instant: {row}"));
    instant_ms(text)
}

/// One stream of every event, ordered by the event-time column `by`; each
/// stream must already be in that order, and equal times keep the streams' order.
pub fn merge(streams: Vec<Vec<Value>>, by: &str) -> Vec<Value> {
    let mut all = Vec::new();
    for (index, stream) in streams.into_iter().enumerate() {
        let mut last = i64::MIN;
        for (position, row) in stream.into_iter().enumerate() {
            let at = time_of(&row, by);
            assert!(
                at >= last,
                "stream {index} is not in `{by}` order at event {position}"
            );
            last = at;
            all.push((at, index, position, row));
        }
    }
    all.sort_by_key(|(at, index, position, _)| (*at, *index, *position));
    all.into_iter().map(|(.., row)| row).collect()
}

/// The events with a watermark after each one, at the latest event time seen
/// minus `lag`, added only when it moves forward.
pub fn with_watermarks(rows: impl IntoIterator<Item = Value>, by: &str, lag: &str) -> Vec<Item> {
    let back = duration_ms(lag);
    let (mut newest, mut current) = (i64::MIN, i64::MIN);
    let mut out = Vec::new();
    for row in rows {
        newest = newest.max(time_of(&row, by));
        out.push(Item::Event(row));
        if newest - back > current {
            current = newest - back;
            out.push(Item::Watermark(rfc3339(current)));
        }
    }
    out
}

/// Events from a JSON Lines file, one object per line.
pub fn read_jsonl(path: impl AsRef<Path>) -> std::io::Result<Vec<Value>> {
    let path = path.as_ref();
    let text = std::fs::read_to_string(path)?;
    text.lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .map(|(n, line)| match serde_json::from_str::<Value>(line) {
            Ok(value @ Value::Object(_)) => Ok(value),
            _ => Err(std::io::Error::other(format!(
                "{}:{}: expected a JSON object per line",
                path.display(),
                n + 1
            ))),
        })
        .collect()
}

/// A CSV cell as a fixture holds it: empty is null, `true`/`false` booleans,
/// numbers numbers (exact digits kept), anything else a string.
fn cell(text: &str) -> Value {
    match text {
        "" => Value::Null,
        "true" => Value::Bool(true),
        "false" => Value::Bool(false),
        _ => match serde_json::from_str::<Value>(text) {
            Ok(number @ Value::Number(_)) => number,
            _ => Value::String(text.to_string()),
        },
    }
}

/// Split one CSV line, with `"quoted, fields"` and `""` for a quote.
fn fields(line: &str) -> Vec<String> {
    let (mut out, mut field, mut quoted) = (Vec::new(), String::new(), false);
    let mut chars = line.chars().peekable();
    while let Some(c) = chars.next() {
        match (c, quoted) {
            ('"', true) if chars.peek() == Some(&'"') => {
                field.push('"');
                chars.next();
            }
            ('"', _) => quoted = !quoted,
            (',', false) => out.push(std::mem::take(&mut field)),
            _ => field.push(c),
        }
    }
    out.push(field);
    out
}

/// Events from a CSV file with a header row. `strings` names columns kept as
/// text, such as a string column of digits. Fields may not contain line breaks.
pub fn read_csv(path: impl AsRef<Path>, strings: &[&str]) -> std::io::Result<Vec<Value>> {
    let text = std::fs::read_to_string(path)?;
    let mut lines = text.lines().filter(|l| !l.is_empty());
    let header = lines.next().map(fields).unwrap_or_default();
    Ok(lines
        .map(|line| {
            let row: Map<String, Value> = header
                .iter()
                .zip(fields(line))
                .map(|(name, text)| {
                    let value = if strings.contains(&name.as_str()) {
                        Value::String(text)
                    } else {
                        cell(&text)
                    };
                    (name.clone(), value)
                })
                .collect();
            Value::Object(row)
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn instants_round_trip() {
        for text in [
            "1970-01-01T00:00:00Z",
            "2026-08-30T10:04:59.999Z",
            "2024-02-29T23:59:59Z",
        ] {
            assert_eq!(rfc3339(instant_ms(text)), text);
        }
        assert_eq!(
            rfc3339(instant_ms("2026-08-30T10:00:00.5Z")),
            "2026-08-30T10:00:00.500Z"
        );
    }

    #[test]
    fn merge_and_watermarks() {
        let a = timed(
            (0..3).map(|_| json!({"c": 1})),
            "t",
            "2026-08-30T10:00:00Z",
            "2m",
        );
        let b = timed(
            (0..2).map(|_| json!({"c": 2})),
            "t",
            "2026-08-30T10:01:00Z",
            "2m",
        );
        let merged = merge(vec![a, b], "t");
        let order: Vec<i64> = merged.iter().map(|r| r["c"].as_i64().unwrap()).collect();
        assert_eq!(order, [1, 2, 1, 2, 1]);
        let stream = with_watermarks(merged, "t", "1m");
        assert_eq!(stream[1], Item::Watermark("2026-08-30T09:59:00Z".into()));
    }

    #[test]
    fn csv_cells_are_typed() {
        assert_eq!(
            fields(r#"1,"a, b","say ""hi""""#),
            ["1", "a, b", r#"say "hi""#]
        );
        assert_eq!(cell("10.50"), json!(10.5));
        assert_eq!(cell(""), Value::Null);
        assert_eq!(cell("x1"), json!("x1"));
    }
}
