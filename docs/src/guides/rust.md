# In Rust

The crate has the same model as the Python package, with `serde_json::json!` rows and assertions that panic, pointing at the test that failed.

```toml
[dev-dependencies]
streamform-test = { git = "https://github.com/glyf-data/streamform-test", tag = "v0.1.0" }
serde_json = "1"
```

```rust
use serde_json::json;
use streamform_test::StreamSql;

fn totals() -> StreamSql {
    StreamSql::new("SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id")
        .source("orders", json!({"customer_id": "int64", "amount": "decimal(12,2)"}))
        .key(&["customer_id"])
}

#[test]
fn each_order_updates_the_total() {
    totals()
        .fixture().unwrap()
        .events([json!({"customer_id": 42, "amount": 10}), json!({"customer_id": 42, "amount": 18})])
        .expect([
            json!({"op": "insert", "customer_id": 42, "total": 10}),
            json!({"op": "update", "customer_id": 42, "total": 28}),
        ])
        .run().unwrap()
        .assert_passed();
}
```

| Python | Rust |
|---|---|
| `StreamSQL(sql, sources={...}, key=..., window=...)` | `StreamSql::new(sql).source(name, json!(...)).key(&[..]).window("5m")` |
| `query.event(...)` | `query.fixture()?.event(json!(...))` |
| `run.assert_final_state("k", {...})` | `run.assert_final_state(&["k"], &[json!(...)])` |
| `run.changelog` | `run.changelog: Vec<Change>` |
| `events.timed`, `merge`, `with_watermarks`, `read_csv`, `read_jsonl` | `streamform_test::events::{timed, merge, with_watermarks, read_csv, read_jsonl}` |
| `repeat`, `product`, `random_rows` | iterators: `(0..1000).map(\|i\| json!(...))` |

Errors from the engine are `streamform_test::Error`; assertions panic with `#[track_caller]`.

The crate finds the engine through `STREAMFORM_BIN` or `streamform` on `PATH`; `pip install streamform` is the simplest way to get it.
