//! Late events and windows: an event behind the watermark is dropped and listed.

use serde_json::json;
use streamform_test::StreamSql;

#[test]
fn a_late_order_is_dropped_and_the_window_closes() {
    let late = json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"});
    StreamSql::new(
        "SELECT customer_id, window_start, window_end, SUM(amount) AS total \
         FROM source('orders') GROUP BY customer_id, window_start, window_end",
    )
    .source(
        "orders",
        json!({"schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
               "event_time": "ordered_at"}),
    )
    .window("5m")
    .fixture()
    .unwrap()
    .event(json!({"customer_id": 42, "amount": 60, "ordered_at": "2026-08-30T10:01:00Z"}))
    .watermark("2026-08-30T10:05:00Z")
    .event(late.clone())
    .run()
    .unwrap()
    .assert_late(&[late])
    .assert_changelog_contains(&[json!({"op": "insert", "customer_id": 42, "total": 60,
        "window_start": "2026-08-30T10:00:00Z", "window_end": "2026-08-30T10:05:00Z"})]);
}
