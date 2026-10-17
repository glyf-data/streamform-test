# Changelogs and state

A batch query returns a table. A streaming query returns a **changelog**: the sequence of changes that keeps its result table up to date as events arrive. Every test in `streamform-test` is about that changelog, or the state it leaves.

## Three kinds of change

| Change | Meaning | Example |
|---|---|---|
| `insert` | A row appears | Customer 42's first order: `total=10` |
| `update` | A row's values change; `before` holds the old row | Their second order: `total=28` |
| `delete` | A row leaves the result | A refund takes them under a `HAVING` threshold |

A query that only filters and projects (`SELECT ... WHERE ...`) emits inserts and nothing else: each event in, at most one row out. It is **append**.

A query that aggregates (`GROUP BY`) emits inserts, updates and deletes: the result is a table keyed by the group. It is **keyed**, and its key is the `GROUP BY` columns. In a test, `key=` says so:

```python
StreamSQL("SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
          sources=..., key="customer_id")
```

Leave the key off an aggregate and the engine says what is wrong: `materialized as append, but its output changelog is Upsert(customer_id)`.

## The final state

Whoever reads a keyed result (a Kafka consumer of an upsert topic, a table kept in sync) holds, for each key, the last row written, and nothing for a key whose last change was a delete. That is the **final state**, and it is often the simplest thing to assert:

```python
run.assert_final_state("customer_id",
    {"customer_id": 7, "total": 120})          # 42 is absent: its row was deleted
```

## Order

The engine emits changes in one order. A real topic keyed by `customer_id` keeps each customer's changes in order, but may interleave customers differently. So there are three strengths of assertion:

| Assertion | Holds when |
|---|---|
| The exact changelog | Every change, in exactly this order |
| Each key's changes in order | Each key's own sequence matches; keys interleave freely |
| The final state | Only the end result per key matters |

Choose the weakest one that still says what the test is about: it keeps the test true under any correct interleaving. [Assertions](../guides/assertions.md) has all of them.

## Values

Values come back typed by the query's output columns: decimals as exact strings (`"28"`, `"13.5"`), timestamps as RFC 3339 (`"2026-08-30T10:00:00.000Z"`), integers and booleans as themselves. Assertions compare by meaning, so `28`, `28.0`, `"28"` and `Decimal("28.00")` all match a decimal 28, and `"2026-08-30T10:00:00Z"` matches `"2026-08-30T10:00:00.000Z"`.
