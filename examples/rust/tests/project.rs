//! A project's own models, and every fixture in its `tests/` under `cargo test`.

use serde_json::json;
use streamform_test::{Project, assert_project_passes};

const SHOP: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../shop");

#[test]
fn every_fixture_in_tests_passes() {
    assert_project_passes(SHOP);
}

#[test]
fn a_customer_total() {
    Project::open(SHOP)
        .unwrap()
        .fixture("customer_metrics")
        .events([
            json!({"customer_id": 42, "amount": 10}),
            json!({"customer_id": 42, "amount": 18}),
        ])
        .run()
        .unwrap()
        .assert_final_state(
            &["customer_id"],
            &[json!({"customer_id": 42, "total_spend": 28})],
        );
}
