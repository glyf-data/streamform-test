"""The pytest plugin, run in a pytester sandbox."""

import shutil
from pathlib import Path

pytest_plugins = ["pytester"]

PROJECTS = Path(__file__).resolve().parents[2] / "testdata" / "projects"


def test_fixture_files_beside_streamform_yml_become_tests(pytester):
    shutil.copytree(PROJECTS / "windowed-metrics", pytester.path / "windowed-metrics")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines(["*tests/late_orders.yml::late_orders PASSED*"])


def test_a_failing_fixture_file_reports_the_binarys_problem(pytester):
    project = pytester.path / "customer-metrics"
    shutil.copytree(PROJECTS / "customer-metrics", project)
    fixture = project / "tests" / "customer_metrics.yml"
    fixture.write_text(fixture.read_text().replace("total_spend: 28", "total_spend: 27"))
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*rows[[]1[]]: total_spend: expected 27, got 28*"])


def test_the_streamform_project_fixture_opens_the_configured_project(pytester):
    shutil.copytree(PROJECTS / "customer-metrics", pytester.path / "customer-metrics")
    pytester.makeini("[pytest]\nstreamform_project = customer-metrics\n")
    pytester.makepyfile(
        test_model="""
def test_total(streamform_project):
    run = streamform_project.fixture("customer_metrics").event(customer_id=1, amount=3).run()
    run.assert_final_state("customer_id", {"customer_id": 1, "total_spend": 3})
"""
    )
    result = pytester.runpytest("test_model.py")
    result.assert_outcomes(passed=1)
