"""The library against the real binary, over the example projects in testdata/.

Run with STREAMFORM_BIN pointing at a streamform that has `test --fixture`.
"""

import time
from decimal import Decimal
from pathlib import Path

import pytest

from streamform_test import Project, StreamformError

PROJECTS = Path(__file__).resolve().parents[2] / "testdata" / "projects"
METRICS = Project(PROJECTS / "customer-metrics")
WINDOWS = Project(PROJECTS / "windowed-metrics")


def test_a_late_order_is_dropped_in_ten_lines():
    # The P4 success criterion: a late-event test for a model in ten lines.
    run = (WINDOWS.fixture("spend_per_5m")
           .event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
           .watermark("2026-08-30T10:04:59.999Z")
           .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
           .run())
    run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
    run.assert_final_state(["customer_id", "window_start"],
        {"customer_id": 42, "window_start": "2026-08-30T10:00:00Z",
         "window_end": "2026-08-30T10:05:00Z", "total_spend": 60, "orders": 1})


def test_it_runs_in_well_under_a_second():
    started = time.perf_counter()
    METRICS.fixture("customer_metrics").event(customer_id=42, amount=10).run()
    assert time.perf_counter() - started < 1.0


def test_the_exact_changelog_is_compared_by_the_binary():
    run = (METRICS.fixture("customer_metrics")
           .event(customer_id=42, amount=10)
           .event(customer_id=42, amount=18)
           .expect({"op": "insert", "customer_id": 42, "total_spend": 10},
                   {"op": "update", "customer_id": 42, "total_spend": 28})
           .run())
    run.assert_passed()
    assert [c.op for c in run.changelog] == ["insert", "update"]
    assert run.changelog[1].before == {"customer_id": 42, "total_spend": "10"}


def test_a_wrong_expectation_names_the_column_and_shows_the_changelog():
    run = (METRICS.fixture("customer_metrics")
           .event(customer_id=42, amount=10)
           .event(customer_id=42, amount=18)
           .expect({"op": "insert", "customer_id": 42, "total_spend": 10},
                   {"op": "update", "customer_id": 42, "total_spend": 27})
           .run())
    with pytest.raises(AssertionError, match=r"rows\[1\]: total_spend: expected 27, got 28"):
        run.assert_passed()


def test_without_expectations_a_run_observes_and_passes():
    run = METRICS.fixture("customer_metrics").event(customer_id=7, amount=1).run()
    run.assert_passed()
    assert len(run.changelog) == 1


def test_per_key_order_ignores_the_order_between_keys():
    run = (METRICS.fixture("customer_metrics")
           .events([{"customer_id": 1, "amount": 5}, {"customer_id": 2, "amount": 7},
                    {"customer_id": 1, "amount": 5}])
           .run())
    run.assert_changelog_per_key("customer_id",
        {"op": "insert", "customer_id": 2, "total_spend": 7},
        {"op": "insert", "customer_id": 1, "total_spend": 5},
        {"op": "update", "customer_id": 1, "total_spend": 10})
    with pytest.raises(AssertionError, match="key"):
        run.assert_changelog_per_key("customer_id",
            {"op": "insert", "customer_id": 1, "total_spend": 5},
            {"op": "insert", "customer_id": 2, "total_spend": 7})


def test_final_state_compares_values_by_meaning():
    run = (METRICS.fixture("customer_metrics")
           .event(customer_id=42, amount=Decimal("10.50"))
           .event(customer_id=42, amount=2.5)
           .run())
    run.assert_final_state("customer_id", {"customer_id": 42, "total_spend": "13.0"})
    assert run.final_state("customer_id")[(42,)]["total_spend"] == "13"
    with pytest.raises(AssertionError, match="final state"):
        run.assert_final_state("customer_id", {"customer_id": 42, "total_spend": 14})


def test_contains_finds_changes_in_order_among_others():
    run = (METRICS.fixture("customer_metrics")
           .event(customer_id=1, amount=1).event(customer_id=2, amount=2)
           .event(customer_id=1, amount=1)
           .run())
    run.assert_changelog_contains({"op": "insert", "customer_id": 1, "total_spend": 1},
                                  {"op": "update", "customer_id": 1, "total_spend": 2})
    with pytest.raises(AssertionError):
        run.assert_changelog_contains({"op": "update", "customer_id": 1, "total_spend": 2},
                                      {"op": "insert", "customer_id": 1, "total_spend": 1})


def test_expect_late_is_compared_by_the_binary():
    run = (WINDOWS.fixture("spend_per_5m")
           .event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
           .watermark("2026-08-30T10:04:59.999Z")
           .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
           .expect_late()
           .run())
    with pytest.raises(AssertionError, match=r"late\[0\]"):
        run.assert_passed()


def test_an_unknown_model_is_an_error_from_the_binary():
    with pytest.raises(StreamformError, match="does not exist"):
        METRICS.fixture("nope").event(customer_id=1, amount=1).run()


def test_a_fixture_can_be_written_and_run_by_the_binary_as_a_file(tmp_path):
    fixture = (METRICS.fixture("customer_metrics").event(customer_id=42, amount=10)
               .expect({"op": "insert", "customer_id": 42, "total_spend": 10}))
    path = fixture.write(tmp_path / "kept.yml")
    assert '"model": "customer_metrics"' in path.read_text()


def test_the_project_runs_its_own_tests():
    assert WINDOWS.test()["passed"] is True


def test_a_directory_without_streamform_yml_is_refused(tmp_path):
    with pytest.raises(StreamformError, match="no streamform.yml"):
        Project(tmp_path)
