# streamform-test

**Unit tests for streaming SQL and streaming data quality.** Write the query, feed it events in pytest or `cargo test`, and assert what it emits: every insert, update and delete, the final state per key, the events it dropped as late, the bad records it set aside. Tests run in milliseconds on a laptop or in CI, with no Kafka, no Flink and no Docker.

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

## Why streaming queries need their own tests

A streaming query is not a batch query that runs often. Its result changes while events arrive, and the ways it changes are where the bugs are:

- A total is **inserted**, then **updated** with every order. A consumer that only reads inserts sees the first value forever.
- A row that stops matching a filter is **deleted**. Forget that, and a "big customers" table keeps customers who got a refund.
- A five-minute window emits **only when event time passes its end**, not when the clock does.
- An order that arrives after the window closed is **late**, and it is dropped. Nothing tells you, unless something counts it.
- A record without a customer cannot be grouped. It has to **go somewhere** other than your totals.

Testing that against a real cluster is slow, flaky, and silent about what was dropped. `streamform-test` runs the query in a deterministic streaming engine and shows all of it: the changelog, the state, the late events, and the records that broke a rule. The same input always gives the same output, so a failing test fails again.

## What you get

- **A query, a source schema, a few events: a test.** No project to set up. [Your first test](getting-started/first-test.md)
- **Assertions that fit streams.** The exact changelog, changes in order among others, each key's order, the final state per key. [Assertions](guides/assertions.md)
- **Event time made testable.** Watermarks, windows that close, late events listed exactly. [Event time](concepts/event-time.md)
- **Data quality at the input.** `not_null` and `check` contracts, with every record that broke one reported. [Testing data quality](guides/data-quality.md)
- **Inputs built in code.** Loops, seeded generators, CSV and JSON Lines files, streams merged by event time. [Building event streams](guides/event-streams.md)
- **Your runner.** A pytest plugin, and a Rust crate for `cargo test`. [pytest](guides/pytest.md), [Rust](guides/rust.md)

## Powered by Streamform

The engine underneath is Streamform's, which compiles the same SQL to Apache Flink and runs it in production. You do not need Streamform to use `streamform-test`; the engine is installed with it. If you later run your queries with Streamform, the tests keep working against your project. [How it works](reference/how-it-works.md)
