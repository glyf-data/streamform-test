# streamform-test

Write streaming tests in Python or Rust, and run them in the free `streamform` binary: events and watermarks in, the exact changelog out, late and quarantined events accounted for. Tests run in-process in the binary's deterministic simulator, in milliseconds, with no Kafka, no Flink and no Docker.

```python
from streamform_test import Project

def test_a_late_order_is_dropped():
    run = (Project("examples/windowed-metrics").fixture("spend_per_5m")
           .event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
           .watermark("2026-08-30T10:04:59.999Z")
           .event(customer_id=42, amount=5, ordered_at="2026-08-30T10:03:00Z")
           .run())
    run.assert_late({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})
    run.assert_final_state(["customer_id", "window_start"],
        {"customer_id": 42, "window_start": "2026-08-30T10:00:00Z",
         "window_end": "2026-08-30T10:05:00Z", "total_spend": 60, "orders": 1})
```

## How it works

The library is a client of the binary. It builds a fixture (the same document as a project's `tests/*.yml`), runs `streamform test --fixture - --json --project DIR` with the fixture on stdin, and reads the test report. It never contains the compiler or the simulator, and never runs SQL itself: the Python package has no dependencies, and the Rust crate depends on `serde_json` only.

Two kinds of assertion:

- **Exact, by the binary.** `expect(...)`, `expect_late(...)` and `expect_quarantined(...)` go into the fixture; the binary compares them with the same typed rules as `streamform test` (an integer `28` matches a decimal `28.000000000`). `assert_passed()` lists every difference.
- **Looser, by the library**, over the changelog the report carries: `assert_changelog_contains` (these changes, in order, among others), `assert_changelog_per_key` (each key's changes in order, any order between keys: what a keyed topic guarantees), `final_state` and `assert_final_state` (each key's last row, deletes removed: what a keyed consumer holds), `assert_late`, `assert_quarantined`. Values compare by meaning: `60`, `60.0` and `"60"` are the same decimal, and `10:00:00Z` is `10:00:00.000Z`.

## Requirements

A `streamform` with `test --fixture` (0.9 or newer), on `PATH` or named by `STREAMFORM_BIN`. An older binary gets a clear error, not a wrong result.

## Python

Python 3.13 or newer.

```bash
pip install streamform-test            # not yet on PyPI: pip install ./python
```

- `Project(path).fixture(model)` starts a fixture; `.event(**columns)`, `.events(rows)`, `.watermark(at)`, `.expect(*changes)`, `.expect_late(*rows)`, `.expect_quarantined(*rows)`, then `.run()`.
- `Fixture.write(path)` saves a fixture as a file, for example into the project's `tests/` to keep it.
- `Project(path).test()` runs the project's own fixtures and returns the report.

**pytest plugin**, loaded automatically once the package is installed:

- Every `tests/*.yml` beside a `streamform.yml`, in the paths pytest collects, is a test of its own, with the binary's differences as the failure message.
- The `streamform_project` fixture opens the project named by `--streamform-project` or the `streamform_project` ini option (default: the root directory).

## Rust

```toml
[dev-dependencies]
streamform-test = { git = "https://github.com/glyf-data/streamform-test" }   # not yet on crates.io
serde_json = "1"
```

The same model, with `serde_json::json!` rows and panicking assertions for `#[test]`:

```rust
use serde_json::json;
use streamform_test::Project;

#[test]
fn totals_per_customer() {
    Project::open(".").unwrap()
        .fixture("customer_metrics")
        .events([json!({"customer_id": 1, "amount": 5}), json!({"customer_id": 1, "amount": 5})])
        .run().unwrap()
        .assert_final_state(&["customer_id"], &[json!({"customer_id": 1, "total_spend": 10})]);
}
```

`streamform_test::assert_project_passes(".")` in one `#[test]` runs every fixture in `tests/` under `cargo test`.

## Developing

```bash
export STREAMFORM_BIN=/path/to/streamform     # 0.9 or newer
cd python && uv venv -p 3.13 && uv pip install -e '.[pytest]' && .venv/bin/python -m pytest
cd rust && cargo test && cargo clippy --all-targets -- -D warnings
```

`testdata/projects/` holds two example projects, copied from Streamform's examples.

## Licence

Apache-2.0. The `streamform` binary it drives has its own terms of use.
