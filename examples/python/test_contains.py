"""Changes in order, among others: assert what matters, ignore the rest.

`assert_changelog_contains` passes when the listed changes appear in this
order, with any other changes before, between or after them. Use it for
the one transition a test is about.
"""

from streamform_test import StreamSQL

totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)


def test_a_customer_crosses_100():
    run = (totals.event(customer_id=7, amount=60)
                 .event(customer_id=42, amount=5)
                 .event(customer_id=7, amount=50)
                 .run())
    run.assert_changelog_contains(
        {"op": "insert", "customer_id": 7, "total": 60},
        {"op": "update", "customer_id": 7, "total": 110},
    )
