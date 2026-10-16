"""Bring your own SQL: queries tested without a project on disk."""

import pytest

from streamform_test import StreamformError, StreamSQL

ORDERS = {"customer_id": "int64", "amount": "decimal(12,2)"}


def test_an_aggregate_without_a_project():
    totals = StreamSQL(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
        sources={"orders": ORDERS},
        key="customer_id",
    )
    run = totals.event(customer_id=42, amount=10).event(customer_id=42, amount=5).run()
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 15})
    assert [c.op for c in run.changelog] == ["insert", "update"]


def test_a_filter_is_append_and_the_project_is_reused():
    big = StreamSQL("SELECT customer_id, amount FROM source('orders') WHERE amount > 100",
                    sources={"orders": ORDERS})
    first = big.events([{"customer_id": 1, "amount": 50}, {"customer_id": 2, "amount": 150}]).run()
    second = big.event(customer_id=3, amount=101).run()
    assert [c.columns["customer_id"] for c in first.changelog] == [2]
    assert len(second.changelog) == 1
    assert big.path.exists()


def test_a_window_over_event_time_drops_a_late_order():
    spend = StreamSQL(
        """SELECT customer_id, window_start, window_end, SUM(amount) AS total
           FROM source('orders') GROUP BY customer_id, window_start, window_end""",
        sources={"orders": {"schema": {**ORDERS, "ordered_at": "timestamp"},
                            "event_time": "ordered_at"}},
        window="5m",
    )
    run = (spend.event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
           .watermark("2026-08-30T10:05:00Z")
           .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
           .run())
    run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
    run.assert_changelog_contains({"op": "insert", "customer_id": 42, "total": 60,
                                   "window_start": "2026-08-30T10:00:00Z",
                                   "window_end": "2026-08-30T10:05:00Z"})


def test_exact_expectations_still_go_to_the_binary():
    totals = StreamSQL(
        "SELECT customer_id, COUNT(*) AS orders FROM source('orders') GROUP BY customer_id",
        sources={"orders": ORDERS}, key=["customer_id"],
    )
    (totals.event(customer_id=7, amount=1)
     .expect({"op": "insert", "customer_id": 7, "orders": 1})
     .run().assert_passed())


def test_unsupported_or_wrong_sql_is_the_binarys_error():
    with pytest.raises(StreamformError, match="materialized as append"):
        StreamSQL("SELECT customer_id, SUM(amount) AS t FROM source('orders') GROUP BY customer_id",
                  sources={"orders": ORDERS}).event(customer_id=1, amount=1).run()


def test_the_throwaway_project_is_removed_with_the_query():
    query = StreamSQL("SELECT * FROM source('orders')", sources={"orders": ORDERS})
    path = query.path
    del query
    import gc; gc.collect()
    assert not path.exists()


def test_an_unknown_source_field_is_refused():
    with pytest.raises(ValueError, match="unknown field"):
        StreamSQL("SELECT 1", sources={"orders": {"schema": ORDERS, "evnt_time": "x"}})
