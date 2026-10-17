# Testing a query

`StreamSQL` is a query under test, with the streams it reads.

```python
from streamform_test import StreamSQL

big_orders = StreamSQL(
    "SELECT customer_id, amount FROM source('orders') WHERE amount > 100",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
)
```

## Sources

`sources` maps each name the query reads with `source('name')` to its columns. Column types:

| Type | Values in a test |
|---|---|
| `int32`, `int64` | whole numbers |
| `float64` | numbers |
| `decimal`, `decimal(p,s)` | numbers or `Decimal`; a bare `decimal` is `decimal(38,9)` |
| `string` | strings |
| `boolean` | `True`, `False` |
| `timestamp` | RFC 3339 in UTC (`"2026-08-30T10:00:00Z"`), a `datetime`, or milliseconds since the epoch |

A column an event leaves out is NULL. A column the source does not declare is an error.

To say more about a source than its columns, give the whole definition with `schema` inside:

| Field | Meaning |
|---|---|
| `schema` | The columns, as above |
| `event_time` | The timestamp column that carries event time ([Event time](../concepts/event-time.md)) |
| `watermark` | How far the watermark trails the newest event time, such as `"1m"`; default `"0s"` |
| `late_events` | `"drop"` (default) or `"keep"` |
| `contracts`, `quarantine` | Data quality rules ([Contracts](../concepts/contracts.md)) |

A query may read several sources.

## The shape of the result

| Argument | When | Example |
|---|---|---|
| none | The query filters or projects: each event gives at most one row | `SELECT ... WHERE amount > 100` |
| `key=` | The query aggregates: its result is a table keyed by the `GROUP BY` columns | `key="customer_id"`, `key=["customer_id", "day"]` |
| `window=` | The aggregate is cut into tumbling windows of event time | `window="5m"` |

The engine checks the query against the shape. A mismatch, or SQL it does not support, raises `StreamformError` with the engine's own message before anything runs:

```text
StreamformError: error: project has 1 error; fix them before testing

error: model `query` is materialized as append, but its output changelog is Upsert(customer_id)
```

[SQL you can test](../reference/sql.md) lists what the engine supports.

## Running it

`event`, `events`, `watermark` and `feed` start a test; each returns it, so a test reads top to bottom. `.run()` returns a `Run`.

```python
run = big_orders.event(customer_id=1, amount=50).event(customer_id=2, amount=150).run()
assert [c.columns["customer_id"] for c in run.changelog] == [2]
```

One `StreamSQL` serves any number of tests: define it once at the top of a test module.
