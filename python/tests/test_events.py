"""Event streams: loops, generators, files, and merging by event time."""

from decimal import Decimal

import pytest

from streamform_test import StreamSQL, Watermark
from streamform_test import events as ev

ORDERS = {"schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
          "event_time": "ordered_at"}
WINDOWED = StreamSQL(
    """SELECT customer_id, window_start, window_end, SUM(amount) AS total, COUNT(*) AS orders
       FROM source('orders') GROUP BY customer_id, window_start, window_end""",
    sources={"orders": ORDERS}, window="5m",
)
TOTALS = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}}, key="customer_id",
)


def test_repeat_and_product_build_events_in_a_loop():
    assert ev.repeat(2, {"a": 1}) == [{"a": 1}, {"a": 1}]
    assert ev.repeat(3, lambda i: {"a": i}) == [{"a": 0}, {"a": 1}, {"a": 2}]
    assert len(ev.product(customer_id=[1, 2, 3], amount=[5, 10], currency="EUR")) == 6


def test_a_thousand_orders_from_a_loop_total_up():
    run = TOTALS.fixture().events(
        ev.repeat(1000, lambda i: {"customer_id": i % 10, "amount": 1})).run()
    run.assert_final_state("customer_id", *[{"customer_id": c, "total": 100} for c in range(10)])


def test_timed_steps_event_time():
    rows = ev.timed(ev.repeat(3, {"customer_id": 1}), column="ordered_at",
                    start="2026-08-30T10:00:00Z", every="90s")
    assert [r["ordered_at"] for r in rows] == [
        "2026-08-30T10:00:00Z", "2026-08-30T10:01:30Z", "2026-08-30T10:03:00Z"]


def test_random_rows_are_the_same_for_the_same_seed():
    make = lambda seed: ev.random_rows(
        50, seed=seed, order_id=ev.sequence(), customer_id=ev.choice([1, 2, 3]),
        amount=ev.decimals(1, 100, places=2), qty=ev.integers(1, 5), currency="EUR",
        ordered_at=ev.times("2026-08-30T10:00:00Z", every="10s", jitter="5s"))
    assert make(7) == make(7) and make(7) != make(8)
    rows = make(7)
    assert [r["order_id"] for r in rows[:3]] == [1, 2, 3]
    assert all(Decimal("1") <= r["amount"] <= Decimal("100") for r in rows)
    assert all(r["amount"] == r["amount"].quantize(Decimal("0.01")) for r in rows)


def test_merge_orders_streams_by_event_time():
    a = ev.timed(ev.repeat(3, {"customer_id": 1}), column="ordered_at",
                 start="2026-08-30T10:00:00Z", every="2m")
    b = ev.timed(ev.repeat(2, {"customer_id": 2}), column="ordered_at",
                 start="2026-08-30T10:01:00Z", every="2m")
    merged = ev.merge(a, b, by="ordered_at")
    assert [r["customer_id"] for r in merged] == [1, 2, 1, 2, 1]
    with pytest.raises(ValueError, match="not in `ordered_at` order"):
        ev.merge(list(reversed(a)), by="ordered_at")


def test_with_watermarks_only_moves_forward():
    rows = [{"t": "2026-08-30T10:02:00Z"}, {"t": "2026-08-30T10:01:00Z"}, {"t": "2026-08-30T10:04:00Z"}]
    stream = ev.with_watermarks(rows, by="t", lag="1m")
    assert [i.at for i in stream if isinstance(i, Watermark)] == [
        "2026-08-30T10:01:00Z", "2026-08-30T10:03:00Z"]


def test_merged_streams_with_watermarks_close_windows_and_drop_a_straggler():
    on_time = ev.timed(ev.repeat(6, {"customer_id": 42, "amount": 10}), column="ordered_at",
                       start="2026-08-30T10:00:00Z", every="1m")
    straggler = [{"customer_id": 42, "amount": 99, "ordered_at": "2026-08-30T10:02:30Z"}]
    # The straggler arrives last: after the watermark has passed 10:05.
    stream = ev.with_watermarks(on_time, by="ordered_at", lag="0s") + straggler
    run = WINDOWED.fixture().feed(stream).run()
    run.assert_late(straggler[0])
    run.assert_changelog_contains({"op": "insert", "customer_id": 42, "total": 50, "orders": 5,
                                   "window_start": "2026-08-30T10:00:00Z",
                                   "window_end": "2026-08-30T10:05:00Z"})


def test_csv_and_jsonl_files_feed_a_test(tmp_path):
    (tmp_path / "orders.csv").write_text("customer_id,amount\n42,10.50\n42,4.50\n7,\n")
    rows = ev.read_csv(tmp_path / "orders.csv")
    assert rows[0] == {"customer_id": 42, "amount": Decimal("10.50")} and rows[2]["amount"] is None
    ev.write_jsonl(tmp_path / "orders.jsonl", rows[:2])
    again = ev.read_jsonl(tmp_path / "orders.jsonl")
    run = TOTALS.fixture().events(again).run()
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 15})
    assert ev.read_csv(tmp_path / "orders.csv", types={"customer_id": str})[0]["customer_id"] == "42"


def test_durations_are_written_as_streamform_writes_them():
    assert ev.duration("500ms").total_seconds() == 0.5
    with pytest.raises(ValueError, match="not a duration"):
        ev.duration("5 minutes")
