"""The exact changelog: every change the model emits, in order, compared by the binary.

`expect(...)` goes into the fixture and the binary compares it with the
same typed rules as `streamform test`: the integer 28 matches the decimal
28.00. Use it when the whole sequence matters, including updates.
"""

import pytest

from streamform_test import StreamSQL

totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)


def test_each_order_updates_the_total():
    (totals.event(customer_id=42, amount=10)
           .event(customer_id=42, amount=18)
           .expect({"op": "insert", "customer_id": 42, "total": 10},
                   {"op": "update", "customer_id": 42, "total": 28})
           .run()
           .assert_passed())


def test_a_wrong_expectation_names_the_row_and_the_column():
    run = (totals.event(customer_id=42, amount=10)
                 .event(customer_id=42, amount=18)
                 .expect({"op": "insert", "customer_id": 42, "total": 10},
                         {"op": "update", "customer_id": 42, "total": 27})
                 .run())
    # The failure lists each difference, then everything the model emitted:
    #   rows[1]: total: expected 27, got 28
    with pytest.raises(AssertionError, match=r"rows\[1\]: total: expected 27, got 28"):
        run.assert_passed()
