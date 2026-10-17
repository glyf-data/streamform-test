"""A project's own models: tests in code beside the YAML fixtures.

The `streamform_project` fixture opens the project named in pytest.ini
(`streamform_project = shop`). The plugin also runs every
`shop/tests/*.yml` as a test of its own, so the YAML fixtures and these
tests share one run and one report.
"""

from streamform_test import Project


def test_a_customer_total(streamform_project: Project):
    run = (streamform_project.fixture("customer_metrics")
                             .event(customer_id=42, amount=10)
                             .event(customer_id=42, amount=18)
                             .run())
    run.assert_final_state("customer_id", {"customer_id": 42, "total_spend": 28})


def test_keep_a_generated_fixture(streamform_project: Project, tmp_path):
    # Write a fixture built in code as a YAML file; save it under
    # shop/tests/ to keep it, and `streamform test` runs it too.
    fixture = (streamform_project.fixture("customer_metrics")
                                 .event(customer_id=1, amount=3)
                                 .expect({"op": "insert", "customer_id": 1, "total_spend": 3}))
    path = fixture.write(tmp_path / "one_order.yml")
    assert path.read_text().startswith("{")


def test_the_project_runs_its_own_fixtures(streamform_project: Project):
    assert streamform_project.test()["passed"] is True
