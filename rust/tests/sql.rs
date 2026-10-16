//! Bring your own SQL: queries tested without a project on disk.

use serde_json::json;
use streamform_test::{Error, StreamSql};

fn orders() -> serde_json::Value {
    json!({"customer_id": "int64", "amount": "decimal(12,2)"})
}

#[test]
fn an_aggregate_without_a_project() {
    let run = StreamSql::new(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    )
    .source("orders", orders())
    .key(&["customer_id"])
    .fixture()
    .unwrap()
    .events([
        json!({"customer_id": 42, "amount": 10}),
        json!({"customer_id": 42, "amount": 5}),
    ])
    .run()
    .unwrap();
    run.assert_final_state(&["customer_id"], &[json!({"customer_id": 42, "total": 15})]);
    assert_eq!(run.changelog.len(), 2);
}

#[test]
fn a_window_drops_a_late_order_and_the_project_is_reused_then_removed() {
    let mut spend = StreamSql::new(
        "SELECT customer_id, window_start, window_end, SUM(amount) AS total \
         FROM source('orders') GROUP BY customer_id, window_start, window_end",
    )
    .source(
        "orders",
        json!({"schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
               "event_time": "ordered_at"}),
    )
    .window("5m");
    let first = spend.fixture().unwrap();
    let run = first
        .event(json!({"customer_id": 42, "amount": 60, "ordered_at": "2026-08-30T10:01:00Z"}))
        .watermark("2026-08-30T10:05:00Z")
        .event(json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"}))
        .run()
        .unwrap();
    run.assert_late(&[
        json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"}),
    ]);
    let again = spend.fixture().unwrap();
    let path = again.project_path().to_path_buf();
    drop(spend);
    assert!(path.exists(), "a live fixture keeps the project");
    drop(again);
    assert!(!path.exists(), "the project goes with the last fixture");
}

#[test]
fn wrong_sql_is_the_binarys_error() {
    let error = StreamSql::new(
        "SELECT customer_id, SUM(amount) AS t FROM source('orders') GROUP BY customer_id",
    )
    .source("orders", orders())
    .fixture()
    .unwrap()
    .event(json!({"customer_id": 1, "amount": 1}))
    .run()
    .unwrap_err();
    assert!(
        matches!(error, Error::Refused(ref text) if text.contains("materialized as append")),
        "{error}"
    );
}
