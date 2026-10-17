# streamform-test

**Unit tests for streaming SQL.** Give your query some events, then check what it produced. Tests run in pytest, in milliseconds, on your laptop or in CI. You don't need Kafka, Flink, or Docker.

Requires Python 3.13 or newer on macOS (Apple silicon or Intel) or x86_64 Linux.

```bash
pip install "streamform-test[pytest]"
```

This also installs the engine that runs your queries.

```python
# test_orders.py
from streamform_test import StreamSQL

# The query under test: a running total of order amounts per customer.
totals = StreamSQL(
    """SELECT customer_id, SUM(amount) AS total
       FROM source('orders')
       GROUP BY customer_id""",
    sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
    key="customer_id",
)


def test_a_refund_lowers_the_total():
    run = (
        totals
        .event(customer_id=42, amount=100)   # an order of 100
        .event(customer_id=42, amount=-10)   # then a refund of 10
        .run()
    )
    run.assert_final_state("customer_id", {"customer_id": 42, "total": 90})
```

```text
$ pytest test_orders.py
test_orders.py .                                             [100%]
1 passed in 0.05s
```

You can also check every change the query made along the way, events dropped as late, and bad records set aside by rules on the input. The [README on GitHub](https://github.com/glyf-data/streamform-test#readme) walks through each, and links to the full documentation.

Licence: Apache-2.0. The engine, the `streamform` package, is free to use under its own terms of use.
