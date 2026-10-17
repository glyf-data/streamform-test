//! Contracts: a record that breaks a rule is quarantined with `_contract`, never counted.

use serde_json::json;
use streamform_test::StreamSql;

#[test]
fn bad_orders_are_set_aside() {
    StreamSql::new(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    )
    .source(
        "orders",
        json!({
            "schema": {"customer_id": "int64", "amount": "decimal(12,2)"},
            "contracts": [
                {"name": "has_customer", "not_null": ["customer_id"]},
                {"name": "positive", "check": "amount > 0"}
            ],
            "quarantine": {"topic": "orders-quarantine"}
        }),
    )
    .key(&["customer_id"])
    .fixture()
    .unwrap()
    .events([
        json!({"customer_id": 42, "amount": 10}),
        json!({"amount": 99}),
        json!({"customer_id": 42, "amount": -3}),
    ])
    .run()
    .unwrap()
    .assert_quarantined(&[
        json!({"amount": 99, "_contract": "has_customer"}),
        json!({"customer_id": 42, "amount": -3, "_contract": "positive"}),
    ])
    .assert_final_state(&["customer_id"], &[json!({"customer_id": 42, "total": 10})]);
}
