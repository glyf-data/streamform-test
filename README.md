# streamform-test

**Unit tests for streaming SQL and streaming data quality.** Write the query, feed it events in pytest or `cargo test`, and assert what it emits: every insert, update and delete, the final state per key, the late events it dropped, the bad records it set aside. Tests run in milliseconds on your laptop or in CI, with no Kafka, no Flink and no Docker.

```bash
pip install streamform-test
```

```python
from streamform_test import StreamSQL

totals = StreamSQL(
    """SELECT customer_id, SUM(amount) AS total
       FROM source('orders') GROUP BY customer_id""",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)

def test_a_refund_lowers_the_total():
    run = (totals.event(customer_id=42, amount=100)
                 .event(customer_id=42, amount=-10)
                 .run())
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 90})
```

```text
$ pytest
tests/test_totals.py .                                       [100%]
1 passed in 0.05s
```

**Documentation: [streamform-test docs](docs/src/introduction.md)**, from first test to every assertion.

## Why

A streaming query is not a batch query that runs often. Its result changes as events arrive: a total is inserted, then updated, a row leaves a filter and is deleted, a window closes only when event time passes its end, an order that arrives too late is dropped, a record without a customer must go somewhere. Those behaviours are where streaming bugs live, and they are hard to test against a real cluster: slow, flaky, and silent about what was dropped.

`streamform-test` runs the query in a deterministic streaming engine and shows you all of it:

- **The changelog.** Every insert, update and delete, in order, with the row before each update.
- **The state.** What a keyed consumer of the result holds after every change.
- **Event time.** Watermarks, windows that close, and the exact events dropped as late.
- **Data quality.** Contracts on the input (`not_null`, `check`), and the records each one set aside.

## What a test can say

| | |
|---|---|
| The exact changelog | `.expect({...}, {...}).run().assert_passed()` |
| These changes, in order, among others | `run.assert_changelog_contains({...}, {...})` |
| Each key's changes in order, keys interleaved freely | `run.assert_changelog_per_key("customer_id", ...)` |
| The final state per key | `run.assert_final_state("customer_id", {...})` |
| The events dropped as late | `run.assert_late({...})` |
| The records a contract set aside | `run.assert_quarantined({..., "_contract": "positive"})` |

Inputs are built in code: loops, seeded random generators, CSV and JSON Lines files, and streams merged by event time with watermarks added for you. Every `tests/*.yml` fixture in a project also runs as a pytest test of its own.

## Rust

```toml
[dev-dependencies]
streamform-test = "0.1"
serde_json = "1"
```

```rust
use serde_json::json;
use streamform_test::StreamSql;

#[test]
fn a_refund_lowers_the_total() {
    StreamSql::new("SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id")
        .source("orders", json!({"customer_id": "int64", "amount": "decimal(12,2)"}))
        .key(&["customer_id"])
        .fixture().unwrap()
        .events([json!({"customer_id": 42, "amount": 100}), json!({"customer_id": 42, "amount": -10})])
        .run().unwrap()
        .assert_final_state(&["customer_id"], &[json!({"customer_id": 42, "total": 90})]);
}
```

## Powered by Streamform

The engine underneath is Streamform, which compiles the same SQL to Apache Flink and runs it in production. You do not need to use Streamform to use `streamform-test`: the engine arrives with `pip install` as the `streamform-bin` package (macOS and x86_64 Linux; elsewhere, install the `streamform` binary and put it on `PATH`). If you later run your queries with Streamform, the tests you wrote keep working against your project's models.

The library is a thin, open client: it builds a test, runs it in the engine, and reads the result. It contains no engine code.

## In this repository

| | |
|---|---|
| [`docs/`](docs/src/introduction.md) | The documentation, as an mdBook |
| [`examples/`](examples/) | A runnable test for every kind of assertion, in Python and Rust |
| [`python/`](python/) | The Python package, Python 3.13 or newer |
| [`rust/`](rust/) | The Rust crate |
| [`bin/`](bin/) | How the `streamform-bin` wheels are built from a Streamform release |

## Developing

```bash
export STREAMFORM_BIN=/path/to/streamform     # 0.9 or newer, or pip install streamform-bin
cd python && uv venv -p 3.13 && uv pip install -e '.[pytest]' && .venv/bin/python -m pytest
cd rust && cargo test && cargo clippy --all-targets -- -D warnings
cd examples && ../python/.venv/bin/python -m pytest && (cd rust && cargo test)
mdbook build docs                              # the documentation, into docs/book/
```

## Releasing

`streamform-bin` is built from a Streamform release's assets, never from source: `bin/build_wheels.py` checks each archive against the release's `checksums.txt` and writes one wheel per platform with the binary and its terms of use.

```bash
gh release download v0.9.0 -R glyf-data/streamform-releases -p 'streamform-*-*.tar.gz' -p checksums.txt -p LICENSE -D assets/
python bin/build_wheels.py --assets assets/ --version 0.9.0 --out dist/
(cd python && uv build --out-dir ../dist)
uvx twine check dist/*
uv publish dist/*                       # streamform-bin first, then streamform-test
(cd rust && cargo publish)
```

## Licence

Apache-2.0. The `streamform` binary that `streamform-bin` carries is free to use under its own terms of use, included in that package.
