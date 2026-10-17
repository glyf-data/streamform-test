# Rust API

```rust
use streamform_test::{StreamSql, Project, Fixture, Run, Change, Error, assert_project_passes};
use streamform_test::events::{self, Item};
```

| Type | |
|---|---|
| `StreamSql` | `new(sql)`, `.source(name, json!(...))`, `.key(&[..])`, `.window(size)`, `.model(name)`, `.fixture() -> Result<Fixture, Error>` |
| `Project` | `open(path) -> Result<Project, Error>`, `.fixture(model)`, `.test() -> Result<Value, Error>` |
| `Fixture` | `.event(json!(...))`, `.events(iter)`, `.watermark(at)`, `.feed(items)`, `.expect(iter)`, `.expect_late(iter)`, `.expect_quarantined(iter)`, `.run() -> Result<Run, Error>`, `.write(path)`, `.to_json()` |
| `Run` | Fields `changelog: Vec<Change>`, `late`, `quarantined`, `report`; `.problems()`, `.assert_passed()`, `.assert_changelog_contains(&[..])`, `.assert_changelog_per_key(&[key], &[..])`, `.changes_by_key(&[key])`, `.final_state(&[key])`, `.assert_final_state(&[key], &[..])`, `.assert_late(&[..])`, `.assert_quarantined(&[..])` |
| `Change` | `op: String`, `columns: Map<String, Value>`, `before: Option<Map<..>>`, `.matches(&json!(...))` |
| `Error` | `NotAProject`, `Binary`, `TooOld`, `Refused` (the engine's message), `Report` |
| `assert_project_passes(path)` | Run every fixture in a project's `tests/`; panic listing each failure |
| `events` | `timed`, `merge`, `with_watermarks`, `read_csv`, `read_jsonl`, `Item::{Event, Watermark}`, `duration_ms`, `instant_ms`, `rfc3339` |

Assertions panic with `#[track_caller]` and return `&Run`, so they chain. Rows are `serde_json::Value` objects; values compare by meaning, as in Python.
