# streamform-test

Write streaming tests in Python or Rust, and run them in the free `streamform` binary: events and watermarks in, the exact changelog out, late and quarantined events accounted for. Tests run in-process in the binary's deterministic simulator, in milliseconds, with no Kafka, no Flink and no Docker.

```python
from streamform_test import Project

def test_a_late_order_is_dropped():
    run = (Project("examples/windowed-metrics").fixture("spend_per_5m")
           .event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
           .watermark("2026-08-30T10:04:59.999Z")
           .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
           .run())
    run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
    run.assert_final_state(["customer_id", "window_start"],
        {"customer_id": 42, "window_start": "2026-08-30T10:00:00Z",
         "window_end": "2026-08-30T10:05:00Z", "total_spend": 60, "orders": 1})
```

## Bring your own SQL

No Streamform project needed: give the query and the columns of what it reads, and test it the same way. The library writes a throwaway project into a temporary directory, runs it in the binary, and removes it afterwards.

```python
from streamform_test import StreamSQL

totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)

def test_a_refund_lowers_the_total():
    run = totals.event(customer_id=42, amount=100).event(customer_id=42, amount=-10).run()
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 90})
```

- `sources` maps each source to its column types (`int32`, `int64`, `float64`, `decimal`, `decimal(p,s)`, `string`, `boolean`, `timestamp`), or to a full source as `sources.yml` holds it: `schema`, `event_time`, `watermark`, `late_events`, `contracts`, `quarantine`.
- `key` makes the result keyed, as an aggregate needs (`materialized: upsert`); without it the result is append, as a filter or a projection is.
- `window="5m"` cuts an aggregate into tumbling windows of event time; the query then selects and groups by `window_start` and `window_end`.
- The query is a Streamform model: `source('orders')` reads a source, and SQL Streamform does not support is refused with the binary's own message.

In Rust: `StreamSql::new(sql).source("orders", json!({...})).key(&["customer_id"]).fixture()?`, then the same fixture methods.

## Building event streams

`streamform_test.events` builds the events a test feeds, so a test can loop, generate, read a file, or merge streams instead of listing every event:

```python
from streamform_test import events as ev

orders = ev.timed(ev.repeat(6, {"customer_id": 42, "amount": 10}),
                  column="ordered_at", start="2026-08-30T10:00:00Z", every="1m")
noise = ev.random_rows(500, seed=7, customer_id=ev.choice([1, 2, 3]),
                       amount=ev.decimals(1, 100), ordered_at=ev.times("2026-08-30T10:00:00Z", every="1s", jitter="5s"))
replay = ev.read_jsonl("samples/orders.jsonl")

stream = ev.with_watermarks(ev.merge(orders, replay, by="ordered_at"), by="ordered_at", lag="1m")
run = project.fixture("spend_per_5m").feed(stream).run()
```

| | |
|---|---|
| Loops | `repeat(n, row)` or `repeat(n, lambda i: {...})`; `product(customer_id=[1, 2], amount=[5, 10])` for every combination |
| Event time | `timed(rows, column=, start=, every="1m")` stamps times in steps |
| Generators | `random_rows(n, seed=, column=generator)` with `choice`, `integers`, `decimals` (exact, with `places`), `sequence` (ids), `times` (stepping, with `jitter` for out-of-order arrival); the same seed gives the same events, so a failure repeats |
| Files | `read_csv(path)` (cells typed as a fixture would: empty is null, numbers are numbers; `types={"zip": str}` keeps a column as text), `read_jsonl(path)`, `write_jsonl(path, rows)` to keep a generated stream |
| Merging | `merge(*streams, by="ordered_at")` interleaves streams already in time order; `with_watermarks(rows, by=, lag="1m")` adds a watermark after each event at the newest time seen minus the lag, only when it moves forward |

`Fixture.feed(stream)` takes the result: dicts are events, `Watermark` items move the watermark. In Rust, loops are iterators (`(0..1000).map(|i| json!({...}))`) and `streamform_test::events` has `timed`, `merge`, `with_watermarks`, `read_jsonl` and `read_csv`, with `Fixture::feed` taking `events::Item`s.

## How it works

The library is a client of the binary. It builds a fixture (the same document as a project's `tests/*.yml`), runs `streamform test --fixture - --json --project DIR` with the fixture on stdin, and reads the test report. It never contains the compiler or the simulator, and never runs SQL itself: the Python package has no dependencies, and the Rust crate depends on `serde_json` only.

Two kinds of assertion:

- **Exact, by the binary.** `expect(...)`, `expect_late(...)` and `expect_quarantined(...)` go into the fixture; the binary compares them with the same typed rules as `streamform test` (an integer `28` matches a decimal `28.000000000`). `assert_passed()` lists every difference.
- **Looser, by the library**, over the changelog the report carries: `assert_changelog_contains` (these changes, in order, among others), `assert_changelog_per_key` (each key's changes in order, any order between keys: what a keyed topic guarantees), `final_state` and `assert_final_state` (each key's last row, deletes removed: what a keyed consumer holds), `assert_late`, `assert_quarantined`. Values compare by meaning: `60`, `60.0` and `"60"` are the same decimal, and `10:00:00Z` is `10:00:00.000Z`.

## Requirements

A `streamform` with `test --fixture` (0.9 or newer), on `PATH` or named by `STREAMFORM_BIN`. An older binary gets a clear error, not a wrong result.

## Python

Python 3.13 or newer.

```bash
pip install streamform-test            # not yet on PyPI: pip install ./python
```

- `Project(path).fixture(model)` starts a fixture; `.event(**columns)`, `.events(rows)`, `.watermark(at)`, `.expect(*changes)`, `.expect_late(*rows)`, `.expect_quarantined(*rows)`, then `.run()`.
- `Fixture.write(path)` saves a fixture as a file, for example into the project's `tests/` to keep it.
- `Project(path).test()` runs the project's own fixtures and returns the report.

**pytest plugin**, loaded automatically once the package is installed:

- Every `tests/*.yml` beside a `streamform.yml`, in the paths pytest collects, is a test of its own, with the binary's differences as the failure message.
- The `streamform_project` fixture opens the project named by `--streamform-project` or the `streamform_project` ini option (default: the root directory).

## Rust

```toml
[dev-dependencies]
streamform-test = { git = "https://github.com/glyf-data/streamform-test" }   # not yet on crates.io
serde_json = "1"
```

The same model, with `serde_json::json!` rows and panicking assertions for `#[test]`:

```rust
use serde_json::json;
use streamform_test::Project;

#[test]
fn totals_per_customer() {
    Project::open(".").unwrap()
        .fixture("customer_metrics")
        .events([json!({"customer_id": 1, "amount": 5}), json!({"customer_id": 1, "amount": 5})])
        .run().unwrap()
        .assert_final_state(&["customer_id"], &[json!({"customer_id": 1, "total_spend": 10})]);
}
```

`streamform_test::assert_project_passes(".")` in one `#[test]` runs every fixture in `tests/` under `cargo test`.

## Developing

```bash
export STREAMFORM_BIN=/path/to/streamform     # 0.9 or newer
cd python && uv venv -p 3.13 && uv pip install -e '.[pytest]' && .venv/bin/python -m pytest
cd rust && cargo test && cargo clippy --all-targets -- -D warnings
```

`testdata/projects/` holds two example projects, copied from Streamform's examples.

## Licence

Apache-2.0. The `streamform` binary it drives has its own terms of use.
