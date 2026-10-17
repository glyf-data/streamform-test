# Data quality contracts

A **contract** is a rule every input record must keep before the query sees it. A record that breaks one never reaches the query: it is **quarantined**, labelled with the rule it broke, and the run reports it.

```python
sources={"orders": {
    "schema": {"customer_id": "int64", "amount": "decimal(12,2)"},
    "contracts": [
        {"name": "has_customer", "not_null": ["customer_id"]},
        {"name": "positive", "check": "amount > 0"},
    ],
    "quarantine": {"topic": "orders-quarantine"},
}}
```

- `not_null` lists columns that must be present.
- `check` is a boolean SQL expression over the record's columns. A record keeps it only when it is **true**: false and unknown (NULL) both break it, so `amount > 0` also sets aside a record with no amount. Write `amount IS NULL OR amount > 0` to let those through.
- Contracts are checked in order; a record is labelled with the first one it broke.
- `quarantine` names where broken records go when the query runs for real (a Kafka topic). In a test it only has to be present.

## Why at the input

A bad record caught after an aggregate has already changed a total, and undoing that is not possible in a stream. Checked at the input, it never counts, and the quarantine is a list someone can read, fix, and replay.

## In a test

```python
run = (totals.event(customer_id=42, amount=10)
             .event(amount=99)                     # no customer
             .event(customer_id=42, amount=-3)     # not positive
             .run())
run.assert_quarantined({"amount": 99, "_contract": "has_customer"},
                       {"customer_id": 42, "amount": -3, "_contract": "positive"})
run.assert_final_state("customer_id", {"customer_id": 42, "total": 10})
```

The total is 10: neither bad record counted. [Testing data quality](../guides/data-quality.md) has more.
