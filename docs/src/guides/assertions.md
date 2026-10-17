# Assertions

A `Run` holds what the query did: `run.changelog` (every change), `run.late` (events dropped as late), `run.quarantined` (records that broke a contract), and `run.report` (the engine's raw report). Assertions read them.

The examples use:

```python
totals = StreamSQL(
    """SELECT customer_id, SUM(amount) AS total
       FROM source('orders') GROUP BY customer_id""",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)
```

## The exact changelog

Every change, in order. Put the expectation into the test before running it, and the engine compares it with its own typed rules:

```python
(totals.event(customer_id=42, amount=10).event(customer_id=42, amount=18)
       .expect({"op": "insert", "customer_id": 42, "total": 10},
               {"op": "update", "customer_id": 42, "total": 28})
       .run()
       .assert_passed())
```

Each expected change names `op` and every output column. A failure lists each difference, then everything the query emitted:

```text
rows[1]: total: expected 27, got 28
```

Use it when the sequence itself is the point: updates, deletes, how many changes.

## Changes in order, among others

```python
run = (totals.event(customer_id=7, amount=60).event(customer_id=42, amount=5)
             .event(customer_id=7, amount=50).run())
run.assert_changelog_contains({"op": "insert", "customer_id": 7, "total": 60},
                              {"op": "update", "customer_id": 7, "total": 110})
```

The listed changes must appear in this order, with anything else around them. Use it for the one transition a test is about.

## Each key's changes in order

```python
run.assert_changelog_per_key("customer_id",
    {"op": "insert", "customer_id": 2, "total": 7},
    {"op": "insert", "customer_id": 1, "total": 5},
    {"op": "update", "customer_id": 1, "total": 10})
```

Every key's own changes, exactly and in order; the order between keys is free. This is what a topic keyed by `customer_id` guarantees, so a test written this way holds however the keys interleave.

## The final state per key

```python
run.assert_final_state("customer_id", {"customer_id": 7, "total": 120})
run.final_state("customer_id")      # {(7,): {"customer_id": 7, "total": "120"}}
```

Each key's last row, without keys whose last change was a delete, in any order: what a keyed consumer holds at the end. A composite key is a list: `assert_final_state(["customer_id", "window_start"], ...)`.

## Late events

```python
run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
```

Exactly these events, in order, were dropped as late. Or put `.expect_late(...)` into the test before `.run()` and the engine compares them, reporting `late[0]: ...` differences through `assert_passed()`.

## Quarantined records

```python
run.assert_quarantined({"amount": 99, "_contract": "has_customer"})
```

Exactly these records broke a contract, each with `_contract`, the first rule it broke. `.expect_quarantined(...)` before `.run()` has the engine compare them.

## How values compare

Assertions compare by meaning. Numbers match across forms (`28`, `28.0`, `"28"`, `Decimal("28.00")`); RFC 3339 instants match across precision (`"10:00:00Z"` and `"10:00:00.000Z"`); strings, booleans and NULL match only themselves. The exact changelog is compared by the engine, with the same rules `streamform test` uses.

## Choosing one

Prefer the weakest assertion that still says what the test is about: the final state over each key's order, each key's order over the exact changelog. A test that asserts only what matters does not break when something that does not matter changes.
