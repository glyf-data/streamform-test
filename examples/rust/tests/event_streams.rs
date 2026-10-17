//! Event streams: loops are iterators; `events` adds time, merging, watermarks and files.

use serde_json::json;
use streamform_test::{StreamSql, events};

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
fn a_loop() {
    let expected: Vec<_> = (0..10)
        .map(|c| json!({"customer_id": c, "total": 100}))
        .collect();
    totals()
        .fixture()
        .unwrap()
        .events((0..1000).map(|i| json!({"customer_id": i % 10, "amount": 1})))
        .run()
        .unwrap()
        .assert_final_state(&["customer_id"], &expected);
}

#[test]
fn orders_from_files() {
    let dir = std::env::temp_dir().join(format!("sf-example-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("orders.csv"),
        "customer_id,amount\n42,10.50\n42,4.50\n",
    )
    .unwrap();
    std::fs::write(
        dir.join("more.jsonl"),
        "{\"customer_id\": 42, \"amount\": 5}\n",
    )
    .unwrap();
    let mut rows = events::read_csv(dir.join("orders.csv"), &[]).unwrap();
    rows.extend(events::read_jsonl(dir.join("more.jsonl")).unwrap());
    std::fs::remove_dir_all(&dir).unwrap();
    totals()
        .fixture()
        .unwrap()
        .events(rows)
        .run()
        .unwrap()
        .assert_final_state(&["customer_id"], &[json!({"customer_id": 42, "total": 20})]);
}

#[test]
fn two_streams_merged_with_watermarks() {
    let orders = events::timed(
        (0..3).map(|_| json!({"customer_id": 42, "amount": 10})),
        "ordered_at",
        "2026-08-30T10:00:00Z",
        "2m",
    );
    let more = events::timed(
        (0..3).map(|_| json!({"customer_id": 42, "amount": 10})),
        "ordered_at",
        "2026-08-30T10:01:00Z",
        "2m",
    );
    let stream = events::with_watermarks(
        events::merge(vec![orders, more], "ordered_at"),
        "ordered_at",
        "0s",
    );
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
    .feed(stream)
    .run()
    .unwrap()
    .assert_changelog_contains(&[json!({"op": "insert", "customer_id": 42, "total": 50,
        "window_start": "2026-08-30T10:00:00Z", "window_end": "2026-08-30T10:05:00Z"})]);
}
