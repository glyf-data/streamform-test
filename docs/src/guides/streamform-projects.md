# Testing a Streamform project

If you run your queries with Streamform, they live in a project: `streamform.yml`, `sources.yml`, and one `models/*.sql` file per query. `streamform-test` tests a project's models directly, with no `StreamSQL` and no copy of the SQL.

```python
from streamform_test import Project

shop = Project("shop")

def test_a_customer_total():
    run = shop.fixture("customer_metrics").event(customer_id=42, amount=10).run()
    run.assert_final_state("customer_id", {"customer_id": 42, "total_spend": 10})
```

`fixture(model)` takes the name of a model; its events go to the source at the top of the model's chain, so a model that reads another model is tested from the original input. Everything else (assertions, event streams, `feed`) is the same.

## Code tests beside YAML fixtures

A project's `tests/*.yml` fixtures run with `streamform test`. With the pytest plugin they also run under pytest, beside tests written in code, in one report. To open the project from a fixture:

```ini
# pytest.ini
[pytest]
streamform_project = shop
```

```python
def test_a_customer_total(streamform_project):
    run = streamform_project.fixture("customer_metrics").event(customer_id=42, amount=10).run()
```

`Fixture.write("shop/tests/one_order.yml")` saves a test built in code as a fixture file, so `streamform test` runs it too. `Project("shop").test()` runs every fixture and returns the report.

In Rust, `streamform_test::assert_project_passes("shop")` in one `#[test]` runs every fixture in `tests/`.

## From StreamSQL to a project

A `StreamSQL` test moves to a project unchanged except for its first line: the query becomes `models/<name>.sql`, its sources go into `sources.yml`, `key` and `window` into `streamform.yml`, and `StreamSQL(...)` becomes `Project("path").fixture("<name>")`.
