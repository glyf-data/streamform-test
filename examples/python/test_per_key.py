"""Each key's changes in order, any order between keys.

A topic keyed by `customer_id` keeps each customer's updates in order but
promises nothing between customers. `assert_changelog_per_key` asserts
exactly that, so the test holds however the keys interleave.
"""

from streamform_test import StreamSQL

totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)


def test_each_customer_in_order():
    run = (totals.event(customer_id=1, amount=5)
                 .event(customer_id=2, amount=7)
                 .event(customer_id=1, amount=5)
                 .run())
    run.assert_changelog_per_key(
        "customer_id",
        # Customer 2 is listed first: the order between keys is free.
        {"op": "insert", "customer_id": 2, "total": 7},
        {"op": "insert", "customer_id": 1, "total": 5},
        {"op": "update", "customer_id": 1, "total": 10},
    )
