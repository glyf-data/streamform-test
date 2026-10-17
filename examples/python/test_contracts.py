"""Contracts: records that break a rule are quarantined, never counted.

A source's contracts are checked before any model reads a record. A record
that breaks one goes to the quarantine with `_contract`, the first rule it
broke, and the run lists it.
"""

from streamform_test import StreamSQL

totals = StreamSQL(
    "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
    sources={"orders": {
        "schema": {"customer_id": "int64", "amount": "decimal(12,2)"},
        "contracts": [
            {"name": "has_customer", "not_null": ["customer_id"]},
            {"name": "positive", "check": "amount > 0"},
        ],
        "quarantine": {"topic": "orders-quarantine"},
    }},
    key="customer_id",
)


def test_bad_orders_are_set_aside():
    run = (totals.event(customer_id=42, amount=10)
                 .event(amount=99)                     # no customer
                 .event(customer_id=42, amount=-3)     # not positive
                 .run())
    run.assert_quarantined(
        {"amount": 99, "_contract": "has_customer"},
        {"customer_id": 42, "amount": -3, "_contract": "positive"},
    )
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 10})


def test_the_binary_compares_the_quarantine():
    (totals.event(customer_id=42, amount=-3)
           .expect_quarantined({"customer_id": 42, "amount": -3, "_contract": "positive"})
           .run()
           .assert_passed())
