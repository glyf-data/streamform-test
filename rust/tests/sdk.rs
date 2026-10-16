//! The crate against the real binary, over the example projects in testdata/.
//!
//! Run with STREAMFORM_BIN pointing at a streamform that has `test --fixture`.

use std::path::PathBuf;
use std::time::Instant;

use serde_json::json;
use streamform_test::{Error, Project, assert_project_passes};

fn project(name: &str) -> Project {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../testdata/projects")
        .join(name);
    Project::open(path).expect("a test project")
}

#[test]
fn a_late_order_is_dropped() {
    let run = project("windowed-metrics")
        .fixture("spend_per_5m")
        .event(json!({"customer_id": 42, "amount": 60, "ordered_at": "2026-08-30T10:01:00Z"}))
        .watermark("2026-08-30T10:04:59.999Z")
        .event(json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"}))
        .run()
        .unwrap();
    run.assert_late(&[
        json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"}),
    ])
    .assert_final_state(
        &["customer_id", "window_start"],
        &[
            json!({"customer_id": 42, "window_start": "2026-08-30T10:00:00Z",
                     "window_end": "2026-08-30T10:05:00Z", "total_spend": 60, "orders": 1}),
        ],
    );
}

#[test]
fn it_runs_in_well_under_a_second() {
    let started = Instant::now();
    project("customer-metrics")
        .fixture("customer_metrics")
        .event(json!({"customer_id": 42, "amount": 10}))
        .run()
        .unwrap();
    assert!(started.elapsed().as_secs_f64() < 1.0);
}

#[test]
fn the_exact_changelog_is_compared_by_the_binary() {
    let run = project("customer-metrics")
        .fixture("customer_metrics")
        .events([
            json!({"customer_id": 42, "amount": 10}),
            json!({"customer_id": 42, "amount": 18}),
        ])
        .expect([
            json!({"op": "insert", "customer_id": 42, "total_spend": 10}),
            json!({"op": "update", "customer_id": 42, "total_spend": 28}),
        ])
        .run()
        .unwrap();
    run.assert_passed();
    assert_eq!(run.changelog[1].op, "update");
    assert_eq!(
        run.changelog[1].before.as_ref().unwrap()["total_spend"],
        "10"
    );
}

#[test]
#[should_panic(expected = "rows[1]: total_spend: expected 27, got 28")]
fn a_wrong_expectation_names_the_column() {
    project("customer-metrics")
        .fixture("customer_metrics")
        .events([
            json!({"customer_id": 42, "amount": 10}),
            json!({"customer_id": 42, "amount": 18}),
        ])
        .expect([
            json!({"op": "insert", "customer_id": 42, "total_spend": 10}),
            json!({"op": "update", "customer_id": 42, "total_spend": 27}),
        ])
        .run()
        .unwrap()
        .assert_passed();
}

#[test]
fn per_key_order_ignores_the_order_between_keys() {
    let run = project("customer-metrics")
        .fixture("customer_metrics")
        .events([
            json!({"customer_id": 1, "amount": 5}),
            json!({"customer_id": 2, "amount": 7}),
            json!({"customer_id": 1, "amount": 5}),
        ])
        .run()
        .unwrap();
    run.assert_changelog_per_key(
        &["customer_id"],
        &[
            json!({"op": "insert", "customer_id": 2, "total_spend": 7}),
            json!({"op": "insert", "customer_id": 1, "total_spend": 5}),
            json!({"op": "update", "customer_id": 1, "total_spend": 10}),
        ],
    )
    .assert_changelog_contains(&[
        json!({"op": "insert", "customer_id": 1, "total_spend": 5}),
        json!({"op": "update", "customer_id": 1, "total_spend": 10}),
    ])
    .assert_final_state(
        &["customer_id"],
        &[
            json!({"customer_id": 1, "total_spend": "10.0"}),
            json!({"customer_id": 2, "total_spend": 7}),
        ],
    );
}

#[test]
#[should_panic(expected = "final state")]
fn a_wrong_final_state_panics() {
    project("customer-metrics")
        .fixture("customer_metrics")
        .event(json!({"customer_id": 1, "amount": 5}))
        .run()
        .unwrap()
        .assert_final_state(
            &["customer_id"],
            &[json!({"customer_id": 1, "total_spend": 6})],
        );
}

#[test]
fn an_unknown_model_is_refused_by_the_binary() {
    let error = project("customer-metrics")
        .fixture("nope")
        .event(json!({"customer_id": 1, "amount": 1}))
        .run()
        .unwrap_err();
    assert!(
        matches!(error, Error::Refused(ref text) if text.contains("does not exist")),
        "{error}"
    );
}

#[test]
fn a_project_runs_its_own_fixtures() {
    assert_project_passes(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../testdata/projects/windowed-metrics"),
    );
}
