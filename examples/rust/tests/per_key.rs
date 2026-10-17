//! Each key's changes in order, any order between keys: what a keyed topic guarantees.

use serde_json::json;
use streamform_test::StreamSql;

#[test]
fn each_customer_in_order() {
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
        json!({"customer_id": 1, "amount": 5}),
        json!({"customer_id": 2, "amount": 7}),
        json!({"customer_id": 1, "amount": 5}),
    ])
    .run()
    .unwrap()
    .assert_changelog_per_key(
        &["customer_id"],
        &[
            json!({"op": "insert", "customer_id": 2, "total": 7}),
            json!({"op": "insert", "customer_id": 1, "total": 5}),
            json!({"op": "update", "customer_id": 1, "total": 10}),
        ],
    );
}
