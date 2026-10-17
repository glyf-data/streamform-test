//! The final state: each key's last row, deletes removed.

use serde_json::json;
use streamform_test::StreamSql;

#[test]
fn a_refund_takes_a_customer_out() {
    let run = StreamSql::new(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') \
         GROUP BY customer_id HAVING SUM(amount) > 100",
    )
    .source(
        "orders",
        json!({"customer_id": "int64", "amount": "decimal(12,2)"}),
    )
    .key(&["customer_id"])
    .fixture()
    .unwrap()
    .events([
        json!({"customer_id": 42, "amount": 140}),
        json!({"customer_id": 7, "amount": 120}),
        json!({"customer_id": 42, "amount": -50}),
    ])
    .run()
    .unwrap();
    // 42 went over 100, then a refund took it back to 90: its row is deleted.
    run.assert_final_state(&["customer_id"], &[json!({"customer_id": 7, "total": 120})]);
}
