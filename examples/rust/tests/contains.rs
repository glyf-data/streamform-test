//! Changes in order, among others: assert the transition a test is about.

use serde_json::json;
use streamform_test::StreamSql;

#[test]
fn a_customer_crosses_100() {
    StreamSql::new(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    )
    .source(
        "orders",
        json!({"customer_id": "int64", "amount": "decimal(12,2)"}),
    )
    .key(&["customer_id"])
    .fixture()
    .unwrap()
    .events([
        json!({"customer_id": 7, "amount": 60}),
        json!({"customer_id": 42, "amount": 5}),
        json!({"customer_id": 7, "amount": 50}),
    ])
    .run()
    .unwrap()
    .assert_changelog_contains(&[
        json!({"op": "insert", "customer_id": 7, "total": 60}),
        json!({"op": "update", "customer_id": 7, "total": 110}),
    ]);
}
