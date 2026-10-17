"""The final state: the table a keyed consumer holds after every change.

`final_state` keeps each key's last row and removes keys whose last change
is a delete; `assert_final_state` compares it with the rows given, in any
order. Values compare by meaning: 90, 90.0 and "90.00" are the same decimal.
"""

from streamform_test import StreamSQL

big_customers = StreamSQL(
    """SELECT customer_id, SUM(amount) AS total FROM source('orders')
       GROUP BY customer_id HAVING SUM(amount) > 100""",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)


def test_a_refund_takes_a_customer_out():
    run = (big_customers.event(customer_id=42, amount=140)
                        .event(customer_id=7, amount=120)
                        .event(customer_id=42, amount=-50)
                        .run())
    # 42 went over 100, then a refund took it back to 90: its row is deleted.
    run.assert_final_state("customer_id", {"customer_id": 7, "total": 120})
    assert (42,) not in run.final_state("customer_id")
