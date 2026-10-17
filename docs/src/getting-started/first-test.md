# Your first test

A test has three parts: the query, the events that go in, and what must come out.

## 1. The query

```python
# test_orders.py
from streamform_test import StreamSQL

totals = StreamSQL(
    """SELECT customer_id, SUM(amount) AS total
       FROM source('orders') GROUP BY customer_id""",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)
```

- `source('orders')` is the stream the query reads. `sources` gives its columns and their types.
- `key="customer_id"` says the result is a table keyed by customer: each customer has one row, updated as orders arrive. An aggregate always needs its `GROUP BY` columns as the key.

## 2. Events in

```python
def test_two_orders():
    run = (totals.event(customer_id=42, amount=10)
                 .event(customer_id=42, amount=18)
                 .run())
```

Events go in in the order written. `.run()` runs them through the engine and returns what came out.

## 3. What came out

```python
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 28})
```

The final state is what someone reading the result keyed by `customer_id` would hold at the end: one row per customer. Run it:

```text
$ pytest test_orders.py
test_orders.py .                                             [100%]
1 passed in 0.05s
```

## What happened on the way

The final state hides how it got there. The changelog shows every step:

```python
    for change in run.changelog:
        print(change)
```

```text
insert customer_id=42 total=10
update customer_id=42 total=28
```

The first order **inserted** a row; the second **updated** it, and `change.before` holds the row as it was. To assert every step, ask for the exact changelog:

```python
def test_each_order_updates_the_total():
    (totals.event(customer_id=42, amount=10)
           .event(customer_id=42, amount=18)
           .expect({"op": "insert", "customer_id": 42, "total": 10},
                   {"op": "update", "customer_id": 42, "total": 28})
           .run()
           .assert_passed())
```

Change `28` to `27` and the failure names the row and the column:

```text
AssertionError: 1 difference(s) from the fixture:
  rows[1]: total: expected 27, got 28

the model emitted:
  1. insert customer_id=42 total=10
  2. update customer_id=42 total=28
```

## Next

- [Changelogs and state](../concepts/changelogs.md): inserts, updates and deletes, and why they matter.
- [Assertions](../guides/assertions.md): every way to say what must come out.
- [Event time and late events](../concepts/event-time.md): windows and lateness.
