# streamform-test

**Unit tests for streaming SQL.** Give your query some events, then check what it produced. Tests run in pytest or `cargo test`, in milliseconds, on your laptop or in CI. You don't need Kafka, Flink, or Docker.

A streaming query doesn't produce one answer at the end. It keeps updating its answer as events arrive: a running total goes up, a refund brings it down, a late event gets dropped, a bad record has to go somewhere. Those in-between steps are where streaming bugs hide, and they are hard to see on a real cluster. `streamform-test` runs your query in a deterministic engine and lets you check every step.

## Quick start

You need **Python 3.13 or newer** on **macOS** (Apple silicon or Intel) or **x86_64 Linux**.

**1. Install it**

```bash
pip install "streamform-test[pytest]"
```

This also installs the engine that runs your queries. There is nothing else to set up.

**2. Write a test.** Save this as `test_orders.py`:

```python
from streamform_test import StreamSQL

# The query under test: a running total of order amounts per customer.
totals = StreamSQL(
    """SELECT customer_id, SUM(amount) AS total
       FROM source('orders')
       GROUP BY customer_id""",
    # The input stream: its name and the type of each column.
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    # The result has one row per customer.
    key="customer_id",
)


def test_a_refund_lowers_the_total():
    run = (
        totals
        .event(customer_id=42, amount=100)   # an order of 100
        .event(customer_id=42, amount=-10)   # then a refund of 10
        .run()
    )
    # At the end, customer 42's total is 90.
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 90})
```

**3. Run it**

```text
$ pytest test_orders.py
test_orders.py .                                             [100%]
1 passed in 0.05s
```

When a check fails, the message shows what the query actually produced:

```text
E   AssertionError: final state has no row {'customer_id': 42, 'total': 100}; it holds:
E     {'customer_id': 42, 'total': '90'}
```

## See every step, not just the end

The final state hides how the query got there. `run.changelog` lists every change the query made, in order:

```python
for change in run.changelog:
    print(change)
```

```text
insert customer_id=42 total=100
update customer_id=42 total=90
```

A downstream system sees exactly these changes, so you can test them too. For example, you can check that a refund produces an update rather than a second row.

## What you can check

| I want to check that... | Use |
|---|---|
| each key ends with the right values | `run.assert_final_state("customer_id", {...})` |
| the query made exactly these changes, in this order | `totals.event(...).expect({...}, {...}).run().assert_passed()` |
| these changes happened in this order, ignoring any others | `run.assert_changelog_contains({...}, {...})` |
| each key changed in this order, with keys free to interleave | `run.assert_changelog_per_key("customer_id", ...)` |
| events that arrived too late were dropped | `run.assert_late({...})` |
| bad records were set aside instead of counted | `run.assert_quarantined({...})` |

Each one has a runnable example in [`examples/`](examples/README.md).

You don't have to type every event by hand. You can generate them in loops or with seeded random generators, read them from CSV or JSON Lines files, and merge several streams by event time ([event streams guide](docs/src/guides/event-streams.md)).

## Catch bad data

Rules on the input, called contracts, set bad records aside before the query sees them. Your test can then check exactly which records were rejected and why:

```python
totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {
        "schema": {"customer_id": "int64", "amount": "decimal(12,2)"},
        "contracts": [
            {"name": "has_customer", "not_null": ["customer_id"]},  # customer_id must be set
            {"name": "positive", "check": "amount > 0"},             # amount must be positive
        ],
        "quarantine": {"topic": "orders-quarantine"},             # where rejected records go
    }},
    key="customer_id",
)


def test_bad_orders_are_set_aside():
    run = (
        totals
        .event(customer_id=42, amount=10)
        .event(amount=99)                    # no customer
        .event(customer_id=42, amount=-3)    # not positive
        .run()
    )
    run.assert_quarantined(
        {"amount": 99, "_contract": "has_customer"},
        {"customer_id": 42, "amount": -3, "_contract": "positive"},
    )
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 10})
```

Each rejected record carries `_contract`, the name of the first rule it broke, and the total only counts the good order.

See the [data quality guide](docs/src/guides/data-quality.md).

## What SQL works

Supported:

- one source per query, with `SELECT`, aliases, arithmetic and `CAST`
- `WHERE` with comparisons, `AND`/`OR`/`NOT`, `IS NULL`, `BETWEEN`, `IN (...)` and `LIKE`
- `CASE`, `||`, and the functions `COALESCE`, `NULLIF`, `UPPER`, `LOWER`, `TRIM`, `LTRIM`, `RTRIM`, `CHAR_LENGTH` and `ABS`
- `GROUP BY` columns or expressions, with `SUM`, `COUNT`, `COUNT(DISTINCT x)`, `MIN`, `MAX` and `AVG`, and `HAVING`
- tumbling windows over event time

Not supported yet: joins from `StreamSQL` (a Streamform project can join two sources), `DISTINCT`, `UNION`, `LIMIT`, `ORDER BY`, date functions, and window functions with `OVER`. A query that uses one of these fails straight away with a message naming it, so a test never runs something different from what you wrote. The full list is in the [SQL reference](docs/src/reference/sql.md).

## Learn more

- [Your first test](docs/src/getting-started/first-test.md): the quick start, explained step by step
- [Checking results](docs/src/guides/assertions.md): every kind of check, and when to use each
- [Event time and late events](docs/src/concepts/event-time.md): watermarks, windows, and what "late" means
- [pytest](docs/src/guides/pytest.md): the plugin, and running a project's `tests/*.yml` files as tests
- [Rust](docs/src/guides/rust.md): the same tests with `cargo test`
- [All documentation](docs/src/introduction.md)

## Rust

The same library is available for Rust. It isn't on crates.io yet, so add it from this repository:

```toml
[dev-dependencies]
streamform-test = { git = "https://github.com/glyf-data/streamform-test", tag = "v0.1.0" }
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

The crate needs the engine on your `PATH`. The simplest way to get it is `pip install streamform`.

## Questions

**Do I need Kafka, Flink or Docker?** No. Tests run entirely on your machine.

**Do I need to use Streamform?** No. The engine underneath is [Streamform](https://pypi.org/project/streamform/), which also compiles the same SQL to Apache Flink for production. You can use `streamform-test` on its own. If you later run your queries with Streamform, the tests you wrote keep working.

**What about Windows or Linux on ARM?** The engine isn't packaged for them yet. If you have a `streamform` binary, put it on your `PATH` or set `STREAMFORM_BIN` to its path.

**Is it open source?** This library is, under Apache-2.0. It contains no engine code: it builds the test, hands it to the engine, and reads the result. The engine, the `streamform` package, is free to use, including commercially, under its own terms of use, which come with that package.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) to set up the repository, run the tests, and make a release.

## Licence

Apache-2.0.
