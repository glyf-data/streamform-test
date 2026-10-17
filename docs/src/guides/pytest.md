# With pytest

Installing `streamform-test` registers a pytest plugin. There is nothing to configure for `StreamSQL` tests: they are ordinary test functions.

## Shared queries

Define a query once per module, or as a fixture in `conftest.py`:

```python
# conftest.py
import pytest
from streamform_test import StreamSQL

@pytest.fixture(scope="session")
def totals():
    return StreamSQL(
        "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
        sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
        key="customer_id",
    )
```

## Parametrized tests

```python
@pytest.mark.parametrize("amounts, total", [([10], 10), ([10, 18], 28), ([100, -10], 90)])
def test_totals(totals, amounts, total):
    run = totals.fixture().events({"customer_id": 1, "amount": a} for a in amounts).run()
    run.assert_final_state("customer_id", {"customer_id": 1, "total": total})
```

## Failures

An assertion raises `AssertionError` with every difference and what the query emitted, so pytest's report shows the full picture. An invalid query or input raises `StreamformError` with the engine's message.

## Fixture files

The plugin also runs fixture files, the YAML form of a test that a [Streamform project](streamform-projects.md) keeps under `tests/`: every `tests/*.yml` beside a `streamform.yml`, in the paths pytest collects, runs as a test of its own.

```text
$ pytest
shop/tests/customer_metrics.yml .                            [ 50%]
tests/test_totals.py .                                       [100%]
```

## Options

| Option | Meaning |
|---|---|
| `streamform_project` in `pytest.ini`, or `--streamform-project` | The project the `streamform_project` fixture opens; default the root directory |
| `STREAMFORM_BIN` | The engine binary to use instead of the installed one |
