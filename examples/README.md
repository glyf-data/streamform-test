# Examples

One file per kind of test, in Python and in Rust. Each runs on its own; the SDK has no CI yet, so run them with the commands below before a change.

| Kind of test | Python | Rust |
|---|---|---|
| The exact changelog, compared by the binary | [test_exact_changelog.py](python/test_exact_changelog.py) | [exact_changelog.rs](rust/tests/exact_changelog.rs) |
| Changes in order, among others | [test_contains.py](python/test_contains.py) | [contains.rs](rust/tests/contains.rs) |
| Each key's changes in order | [test_per_key.py](python/test_per_key.py) | [per_key.rs](rust/tests/per_key.rs) |
| The final state per key | [test_final_state.py](python/test_final_state.py) | [final_state.rs](rust/tests/final_state.rs) |
| Late events and windows | [test_late_events.py](python/test_late_events.py) | [late_events.rs](rust/tests/late_events.rs) |
| Contracts and quarantined events | [test_contracts.py](python/test_contracts.py) | [contracts.rs](rust/tests/contracts.rs) |
| A project's models and its own `tests/*.yml` | [test_project.py](python/test_project.py) | [project.rs](rust/tests/project.rs) |
| Event streams: loops, generators, files, merging | [test_event_streams.py](python/test_event_streams.py) | [event_streams.rs](rust/tests/event_streams.rs) |

`shop/` is the example project the project tests use; its `tests/customer_metrics.yml` is also collected by the pytest plugin as a test of its own.

```bash
export STREAMFORM_BIN=/path/to/streamform    # 0.9 or newer
cd examples && pytest                         # Python
cd examples/rust && cargo test                # Rust
```
