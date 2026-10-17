# Building event streams

A handful of events is written inline. Hundreds, a realistic mix, or a sample from production are built with `streamform_test.events`, and delivered with `feed`:

```python
from streamform_test import events as ev

run = spend_per_5m.fixture().feed(stream).run()
```

A stream is a list: dictionaries are events, `Watermark` items move the watermark. Every helper returns a plain list, so streams compose with ordinary Python (`+`, comprehensions, slicing).

## Loops

```python
ev.repeat(3, {"customer_id": 42, "amount": 10})              # the same event three times
ev.repeat(1000, lambda i: {"customer_id": i % 10, "amount": 1})
ev.product(customer_id=[1, 2], amount=[5, 10], currency="EUR")  # every combination: 4 events
```

## Event time in steps

```python
ev.timed(ev.repeat(6, {"customer_id": 42, "amount": 10}),
         column="ordered_at", start="2026-08-30T10:00:00Z", every="1m")
```

Sets `ordered_at` to 10:00, 10:01, ... 10:05. Durations are written `500ms`, `30s`, `5m`, `2h`, `7d`.

## Generated events

```python
orders = ev.random_rows(
    500, seed=7,
    order_id=ev.sequence(),                       # 1, 2, 3, ...
    customer_id=ev.choice([1, 2, 3]),
    amount=ev.decimals(1, 100, places=2),         # exact decimals
    quantity=ev.integers(1, 5),
    ordered_at=ev.times("2026-08-30T10:00:00Z", every="1s", jitter="5s"),
    currency="EUR",                               # a plain value is the same in every event
)
```

The same `seed` gives the same events on every run, so a failure repeats until it is fixed. `jitter` moves each time up to that much earlier or later: out-of-order arrival, as from a real producer.

## Files

```python
ev.read_csv("samples/orders.csv")
ev.read_jsonl("samples/orders.jsonl")
ev.write_jsonl("samples/generated.jsonl", orders)
```

CSV cells are read as a test would write them: empty is NULL, `true` and `false` are booleans, whole numbers are integers, other numbers are exact decimals, anything else is a string. `types={"zip": str}` keeps a column of digits as text. JSON Lines keeps decimals exact. A sample exported from a real topic as JSON Lines replays as is.

## Merging streams

```python
orders  = ev.timed(ev.repeat(3, {"customer_id": 42, "amount": 10}), column="ordered_at",
                   start="2026-08-30T10:00:00Z", every="2m")
refunds = ev.read_jsonl("samples/refunds.jsonl")
merged  = ev.merge(orders, refunds, by="ordered_at")
```

`merge` interleaves streams that are each already in `by` order into one, by event time. Events at the same time keep the order of the streams as given.

## Watermarks, added for you

```python
stream = ev.with_watermarks(merged, by="ordered_at", lag="1m")
```

Adds a `Watermark` after each event at the newest event time seen so far minus `lag`, only when it moves forward, as a real source does. Anything appended after it that is older than the watermark is late:

```python
straggler = {"customer_id": 42, "amount": 99, "ordered_at": "2026-08-30T10:02:30Z"}
run = spend_per_5m.fixture().feed(ev.with_watermarks(orders, by="ordered_at") + [straggler]).run()
run.assert_late(straggler)
```

`every=10` adds a watermark only after every tenth event.

## In Rust

Loops are iterators: `(0..1000).map(|i| json!({"customer_id": i % 10, "amount": 1}))`. `streamform_test::events` has `timed`, `merge`, `with_watermarks`, `read_csv` and `read_jsonl`; `Fixture::feed` takes `events::Item`s.
