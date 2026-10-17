//! The exact changelog: every change, in order, compared by the binary.

use serde_json::json;
use streamform_test::StreamSql;

fn totals() -> StreamSql {
    StreamSql::new(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    )
    .source(
        "orders",
        json!({"customer_id": "int64", "amount": "decimal(12,2)"}),
    )
    .key(&["customer_id"])
}

#[test]
fn each_order_updates_the_total() {
    totals()
        .fixture()
        .unwrap()
        .events([
            json!({"customer_id": 42, "amount": 10}),
            json!({"customer_id": 42, "amount": 18}),
        ])
        .expect([
            json!({"op": "insert", "customer_id": 42, "total": 10}),
            json!({"op": "update", "customer_id": 42, "total": 28}),
        ])
        .run()
        .unwrap()
        .assert_passed();
}

#[test]
#[should_panic(expected = "rows[1]: total: expected 27, got 28")]
fn a_wrong_expectation_names_the_row_and_the_column() {
    totals()
        .fixture()
        .unwrap()
        .events([
            json!({"customer_id": 42, "amount": 10}),
            json!({"customer_id": 42, "amount": 18}),
        ])
        .expect([
            json!({"op": "insert", "customer_id": 42, "total": 10}),
            json!({"op": "update", "customer_id": 42, "total": 27}),
        ])
        .run()
        .unwrap()
        .assert_passed();
}
