# Event time and late events

Events carry the time they happened, which is not the time they arrive. A query that groups by time windows has to decide when a window is complete, and what to do with an event that arrives after that.

## Event time and the watermark

A source declares which column holds event time:

```python
sources={"orders": {
    "schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
    "event_time": "ordered_at",
}}
```

The **watermark** is the source's statement that no earlier event is still expected. When it passes the end of a window, the window is complete and emits its rows. In a test, you move it explicitly:

```python
.event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
.watermark("2026-08-30T10:05:00Z")      # the 10:00 to 10:05 window closes here
```

A source can also allow for disorder with `"watermark": "1m"`: the watermark then trails the newest event time by a minute. The watermark never moves backwards.

## Windows

`window="5m"` cuts an aggregate into tumbling five-minute windows. The query selects and groups by `window_start` and `window_end`:

```python
spend_per_5m = StreamSQL(
    """SELECT customer_id, window_start, window_end, SUM(amount) AS total
       FROM source('orders') GROUP BY customer_id, window_start, window_end""",
    sources={"orders": {"schema": {...}, "event_time": "ordered_at"}},
    window="5m",
)
```

A window emits one row per key, once, when the watermark reaches its last millisecond. Its result is append: windows do not update after they close.

## Late events

An event behind the watermark is **late**. By default the source drops it (`"late_events": "drop"`), and the run lists it, so a test can say exactly which events were lost:

```python
run = (spend_per_5m.event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
                   .watermark("2026-08-30T10:05:00Z")
                   .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
                   .run())
run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
```

This is the test that catches the silent loss in production: a too-tight watermark, a producer that batches, a partition that lags. With `"late_events": "keep"`, late events are counted in their window instead, and nothing is listed.

[Building event streams](../guides/event-streams.md) shows how to add watermarks automatically, and how to merge several streams by event time.
