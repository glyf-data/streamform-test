//! Event streams fed to a windowed query.

use serde_json::json;
use streamform_test::StreamSql;
use streamform_test::events::{self, Item};

#[test]
fn merged_streams_with_watermarks_close_a_window_and_drop_a_straggler() {
    let mut windowed = StreamSql::new(
        "SELECT customer_id, window_start, window_end, SUM(amount) AS total, COUNT(*) AS orders \
         FROM source('orders') GROUP BY customer_id, window_start, window_end",
    )
    .source(
        "orders",
        json!({"schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
               "event_time": "ordered_at"}),
    )
    .window("5m");
    let a = events::timed(
        (0..3).map(|_| json!({"customer_id": 42, "amount": 10})),
        "ordered_at",
        "2026-08-30T10:00:00Z",
        "2m",
    );
    let b = events::timed(
        (0..3).map(|_| json!({"customer_id": 42, "amount": 10})),
        "ordered_at",
        "2026-08-30T10:01:00Z",
        "2m",
    );
    let straggler = json!({"customer_id": 42, "amount": 99, "ordered_at": "2026-08-30T10:02:30Z"});
    let mut stream =
        events::with_watermarks(events::merge(vec![a, b], "ordered_at"), "ordered_at", "0s");
    stream.push(Item::Event(straggler.clone()));
    let run = windowed.fixture().unwrap().feed(stream).run().unwrap();
    run.assert_late(&[straggler])
        .assert_changelog_contains(&[json!({
            "op": "insert", "customer_id": 42, "total": 50, "orders": 5,
            "window_start": "2026-08-30T10:00:00Z", "window_end": "2026-08-30T10:05:00Z"
        })]);
}

#[test]
fn a_loop_of_a_thousand_orders() {
    let run = StreamSql::new(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    )
    .source(
        "orders",
        json!({"customer_id": "int64", "amount": "decimal(12,2)"}),
    )
    .key(&["customer_id"])
    .fixture()
    .unwrap()
    .events((0..1000).map(|i| json!({"customer_id": i % 10, "amount": 1})))
    .run()
    .unwrap();
    let expected: Vec<_> = (0..10)
        .map(|c| json!({"customer_id": c, "total": 100}))
        .collect();
    run.assert_final_state(&["customer_id"], &expected);
}
