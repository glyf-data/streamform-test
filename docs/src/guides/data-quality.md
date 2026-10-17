# Testing data quality

Streaming data quality has two halves, and a test can cover both: rules on what comes in, and checks on what goes out.

## Rules on the input

[Contracts](../concepts/contracts.md) on a source set aside records that break a rule before the query sees them. Test that each rule catches what it should, and lets through what it should:

```python
orders = {
    "schema": {"order_id": "int64", "customer_id": "int64", "amount": "decimal(12,2)"},
    "contracts": [
        {"name": "has_customer", "not_null": ["customer_id"]},
        {"name": "positive", "check": "amount IS NULL OR amount > 0"},
    ],
    "quarantine": {"topic": "orders-quarantine"},
}
totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": orders}, key="customer_id",
)

def test_bad_orders_never_count():
    run = (totals.event(order_id=1, customer_id=42, amount=10)
                 .event(order_id=2, amount=99)
                 .event(order_id=3, customer_id=42, amount=-3)
                 .run())
    run.assert_quarantined({"order_id": 2, "amount": 99, "_contract": "has_customer"},
                           {"order_id": 3, "customer_id": 42, "amount": -3, "_contract": "positive"})
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 10})

def test_a_missing_amount_is_allowed():
    run = totals.event(order_id=4, customer_id=7).run()
    run.assert_quarantined()                      # nothing set aside
```

## Generated bad data

Rules are best tested against many shapes of bad input. Generate them with a seed, and assert that exactly the bad ones were set aside:

```python
from streamform_test import events as ev

def test_every_negative_amount_is_quarantined():
    rows = ev.random_rows(300, seed=1, order_id=ev.sequence(), customer_id=ev.choice([1, 2]),
                          amount=ev.decimals(-50, 50))
    run = totals.fixture().events(rows).run()
    bad = [r for r in rows if r["amount"] <= 0]
    assert [q["order_id"] for q in run.quarantined] == [r["order_id"] for r in bad]
```

## Checks on the output

Some quality rules are about the result, not the input: no negative totals, every window has at least one order, no customer appears in two rows. Assert them over the final state or the changelog:

```python
def test_totals_never_go_negative():
    rows = ev.random_rows(500, seed=3, customer_id=ev.choice([1, 2, 3]), amount=ev.decimals(1, 100))
    run = totals.fixture().events(rows).run()
    assert all(float(c.columns["total"]) >= 0 for c in run.changelog)
```

## Lost data

Data that is dropped as late is a quality problem too: it never reaches the result and nothing errors. [Event time and late events](../concepts/event-time.md) shows how to assert exactly which events were lost, so a change to the watermark that loses more data fails a test.
