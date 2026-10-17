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

## Kinds of test

Each kind below has a full, runnable example in Python and in Rust under [`examples/`](examples/). The snippets use `totals`, a query keyed by customer:

```python
totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)
```

### The exact changelog

Every change, in order, compared by the binary with `streamform test`'s typing rules. A failure lists each difference (`rows[1]: total: expected 27, got 28`) and everything the model emitted. [Python](examples/python/test_exact_changelog.py) · [Rust](examples/rust/tests/exact_changelog.rs)

```python
(totals.event(customer_id=42, amount=10).event(customer_id=42, amount=18)
       .expect({"op": "insert", "customer_id": 42, "total": 10},
               {"op": "update", "customer_id": 42, "total": 28})
       .run().assert_passed())
```

### Changes in order, among others

The changes a test is about, in this order, with anything else around them. [Python](examples/python/test_contains.py) · [Rust](examples/rust/tests/contains.rs)

```python
run.assert_changelog_contains({"op": "insert", "customer_id": 7, "total": 60},
                              {"op": "update", "customer_id": 7, "total": 110})
```

### Each key's changes in order

What a topic keyed by the key guarantees: each key's changes in order, any order between keys. [Python](examples/python/test_per_key.py) · [Rust](examples/rust/tests/per_key.rs)

```python
run.assert_changelog_per_key("customer_id",
    {"op": "insert", "customer_id": 2, "total": 7},
    {"op": "insert", "customer_id": 1, "total": 5},
    {"op": "update", "customer_id": 1, "total": 10})
```

### The final state per key

The table a keyed consumer holds after every change: each key's last row, keys whose last change is a delete removed, rows in any order. [Python](examples/python/test_final_state.py) · [Rust](examples/rust/tests/final_state.rs)

```python
run.assert_final_state("customer_id", {"customer_id": 7, "total": 120})
run.final_state("customer_id")          # {(7,): {"customer_id": 7, "total": "120"}}
```

### Late events and windows

A window emits a row per key when the watermark passes its end; an event behind the watermark is dropped and listed. [Python](examples/python/test_late_events.py) · [Rust](examples/rust/tests/late_events.rs)

```python
run = (spend_per_5m.event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
                   .watermark("2026-08-30T10:05:00Z")
                   .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
                   .run())
run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
```

`expect_late(...)` before `run()` has the binary compare them instead.

### Contracts and quarantined events

A record that breaks a source's contract never reaches the model; it is quarantined with `_contract`, the first rule it broke. [Python](examples/python/test_contracts.py) · [Rust](examples/rust/tests/contracts.rs)

```python
run.assert_quarantined({"amount": 99, "_contract": "has_customer"},
                       {"customer_id": 42, "amount": -3, "_contract": "positive"})
```

`expect_quarantined(...)` before `run()` has the binary compare them instead.

### A project's models and its YAML fixtures

Tests in code against a project's own models, beside its `tests/*.yml`, in one pytest run. [Python](examples/python/test_project.py) · [Rust](examples/rust/tests/project.rs)

```ini
# pytest.ini
[pytest]
streamform_project = shop
```

```python
def test_a_customer_total(streamform_project):
    run = streamform_project.fixture("customer_metrics").event(customer_id=42, amount=10).run()
    run.assert_final_state("customer_id", {"customer_id": 42, "total_spend": 10})
```

The plugin collects every `shop/tests/*.yml` as a test of its own. `Fixture.write(path)` saves a fixture built in code as a file, to keep it under `tests/`. In Rust, `assert_project_passes("shop")` runs every fixture in one `#[test]`.

### Event streams

Loops, seeded generators, CSV and JSON Lines files, and merging streams by event time with watermarks; see [Building event streams](#building-event-streams). [Python](examples/python/test_event_streams.py) · [Rust](examples/rust/tests/event_streams.rs)

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

A `streamform` with `test --fixture` (0.9 or newer). On macOS (Apple silicon and Intel) and any x86_64 Linux (glibc or musl, Alpine included), `pip install streamform-test` brings it along as the `streamform-bin` package, and the `streamform` command with it. Elsewhere, install the binary yourself. The library looks for it in this order: `STREAMFORM_BIN`, then the binary from `streamform-bin`, then `streamform` on `PATH`. An older binary gets a clear error, not a wrong result.

## Python

Python 3.13 or newer.

```bash
pip install streamform-test            # brings the streamform binary on macOS and Linux x86_64
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
cd examples && ../python/.venv/bin/python -m pytest && (cd rust && cargo test)
```

`testdata/projects/` holds two example projects, copied from Streamform's examples.

## Releasing

`streamform-bin` is built from a Streamform release's assets, never from source: `bin/build_wheels.py` checks each archive against the release's `checksums.txt` and writes one wheel per platform with the binary and the terms of use.

```bash
gh release download v0.9.0 -R glyf-data/streamform-releases -p 'streamform-*-*.tar.gz' -p checksums.txt -p LICENSE -D assets/
python bin/build_wheels.py --assets assets/ --version 0.9.0 --out dist/
(cd python && uv build --out-dir ../dist)
uvx twine check dist/*
uv publish dist/*                       # needs a PyPI token
(cd rust && cargo publish)              # needs a crates.io token
```

Publish `streamform-bin` before `streamform-test`, since the second depends on the first.

## Licence

Apache-2.0. The `streamform` binary it drives has its own terms of use.
