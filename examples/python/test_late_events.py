"""Late events and windows: what event time drops, and what a window emits.

A window emits one row per key when the watermark passes its end. An event
behind the watermark is late: the source drops it, and the run lists it.
Either let the binary compare the late events (`expect_late`), or assert
on them afterwards (`assert_late`).
"""

from streamform_test import StreamSQL

spend_per_5m = StreamSQL(
    """SELECT customer_id, window_start, window_end, SUM(amount) AS total
       FROM source('orders') GROUP BY customer_id, window_start, window_end""",
    sources={"orders": {
        "schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
        "event_time": "ordered_at",
    }},
    window="5m",
)

LATE = {"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"}


def test_a_late_order_is_dropped_and_the_window_closes():
    run = (spend_per_5m.event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
                       .watermark("2026-08-30T10:05:00Z")
                       .event(LATE)
                       .run())
    run.assert_late(LATE)
    run.assert_changelog_contains({"op": "insert", "customer_id": 42, "total": 60,
                                   "window_start": "2026-08-30T10:00:00Z",
                                   "window_end": "2026-08-30T10:05:00Z"})


def test_the_binary_compares_the_late_events():
    (spend_per_5m.event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
                 .watermark("2026-08-30T10:05:00Z")
                 .event(LATE)
                 .expect_late(LATE)
                 .run()
                 .assert_passed())
