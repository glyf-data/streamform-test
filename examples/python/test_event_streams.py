"""Event streams: loops, generators, files, and merging by event time.

`streamform_test.events` builds what a test feeds, and `Fixture.feed`
takes it: dicts are events, `Watermark` items move the watermark.
"""

from streamform_test import StreamSQL
from streamform_test import events as ev

totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)
spend_per_5m = StreamSQL(
    """SELECT customer_id, window_start, window_end, SUM(amount) AS total
       FROM source('orders') GROUP BY customer_id, window_start, window_end""",
    sources={"orders": {
        "schema": {"customer_id": "int64", "amount": "decimal(12,2)", "ordered_at": "timestamp"},
        "event_time": "ordered_at",
    }},
    window="5m",
)


def test_a_loop():
    run = totals.fixture().events(ev.repeat(1000, lambda i: {"customer_id": i % 10, "amount": 1})).run()
    run.assert_final_state("customer_id", *[{"customer_id": c, "total": 100} for c in range(10)])


def test_every_combination():
    run = totals.fixture().events(ev.product(customer_id=[1, 2], amount=[5, 10])).run()
    run.assert_final_state("customer_id", {"customer_id": 1, "total": 15}, {"customer_id": 2, "total": 15})


def test_generated_orders_with_a_seed():
    # The same seed gives the same orders on every run, so a failure repeats.
    orders = ev.random_rows(200, seed=7, customer_id=ev.choice([1, 2, 3]), amount=ev.decimals(1, 100))
    run = totals.fixture().events(orders).run()
    expected = {c: sum(o["amount"] for o in orders if o["customer_id"] == c) for c in (1, 2, 3)}
    run.assert_final_state("customer_id", *[{"customer_id": c, "total": t} for c, t in expected.items()])


def test_orders_from_files(tmp_path):
    (tmp_path / "orders.csv").write_text("customer_id,amount\n42,10.50\n42,4.50\n")
    (tmp_path / "more.jsonl").write_text('{"customer_id": 42, "amount": 5}\n')
    rows = ev.read_csv(tmp_path / "orders.csv") + ev.read_jsonl(tmp_path / "more.jsonl")
    totals.fixture().events(rows).run().assert_final_state("customer_id", {"customer_id": 42, "total": 20})


def test_two_streams_merged_with_watermarks():
    orders = ev.timed(ev.repeat(3, {"customer_id": 42, "amount": 10}),
                      column="ordered_at", start="2026-08-30T10:00:00Z", every="2m")
    more = ev.timed(ev.repeat(3, {"customer_id": 42, "amount": 10}),
                    column="ordered_at", start="2026-08-30T10:01:00Z", every="2m")
    stream = ev.with_watermarks(ev.merge(orders, more, by="ordered_at"), by="ordered_at", lag="0s")
    run = spend_per_5m.fixture().feed(stream).run()
    # 10:00 to 10:04 holds five orders; the 10:05 order opens the next window.
    run.assert_changelog_contains({"op": "insert", "customer_id": 42, "total": 50,
                                   "window_start": "2026-08-30T10:00:00Z",
                                   "window_end": "2026-08-30T10:05:00Z"})
