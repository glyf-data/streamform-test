//! Write streaming tests in Rust; run them in the free `streamform` binary.
//!
//! The crate builds a fixture, runs it with `streamform test --fixture - --json`,
//! and asserts on the report. It never contains the simulator or the compiler:
//! its only dependency is `serde_json`.
//!
//! ```no_run
//! use serde_json::json;
//! use streamform_test::Project;
//!
//! let run = Project::open("examples/windowed-metrics").unwrap()
//!     .fixture("spend_per_5m")
//!     .event(json!({"customer_id": 42, "amount": 60, "ordered_at": "2026-08-30T10:01:00Z"}))
//!     .watermark("2026-08-30T10:04:59.999Z")
//!     .event(json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"}))
//!     .run()
//!     .unwrap();
//! run.assert_late(&[json!({"customer_id": 42, "amount": 5, "ordered_at": "2026-08-30T10:03:00Z"})]);
//! ```
//!
//! The binary is `STREAMFORM_BIN` when set, otherwise `streamform` on `PATH`.

use std::fmt;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde_json::{Map, Value, json};

mod sql;
mod values;

pub use sql::StreamSql;
pub use values::{same, same_row};

/// The environment variable that names the binary.
pub const BINARY_ENV: &str = "STREAMFORM_BIN";

/// The test report version this crate reads.
pub const REPORT_VERSION: u64 = 1;

/// Why a fixture could not be run: the binary, the project, or the fixture.
#[derive(Debug)]
pub enum Error {
    /// The directory has no `streamform.yml`.
    NotAProject(PathBuf),
    /// The binary could not be started.
    Binary(String),
    /// The binary predates `streamform test --fixture`.
    TooOld,
    /// The binary refused to run: the project or the fixture is invalid. The text is its stderr.
    Refused(String),
    /// The binary's output was not a test report this crate reads.
    Report(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::NotAProject(path) => {
                write!(
                    f,
                    "{} is not a Streamform project: no streamform.yml",
                    path.display()
                )
            }
            Error::Binary(why) => write!(
                f,
                "could not run streamform ({why}); install it, or set {BINARY_ENV} to the binary's path"
            ),
            Error::TooOld => write!(
                f,
                "this streamform cannot take a fixture from outside the project's tests/; \
                 streamform-test needs a streamform with `test --fixture` (0.9 or newer)"
            ),
            Error::Refused(stderr) => write!(f, "{stderr}"),
            Error::Report(why) => write!(f, "unreadable test report: {why}"),
        }
    }
}

impl std::error::Error for Error {}

fn binary() -> String {
    std::env::var(BINARY_ENV).unwrap_or_else(|_| "streamform".to_string())
}

/// Run the binary with `args`, `stdin` on its standard input, and return the report.
fn run_binary(args: &[&str], project: &Path, stdin: Option<&str>) -> Result<Value, Error> {
    let mut child = Command::new(binary())
        .args(args)
        .arg("--project")
        .arg(project)
        .stdin(if stdin.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| Error::Binary(e.to_string()))?;
    if let Some(text) = stdin {
        child
            .stdin
            .take()
            .expect("stdin is piped")
            .write_all(text.as_bytes())
            .map_err(|e| Error::Binary(e.to_string()))?;
    }
    let output = child
        .wait_with_output()
        .map_err(|e| Error::Binary(e.to_string()))?;
    // Exit 0: every assertion held. Exit 1: one failed, and the report says
    // which. Exit 2: nothing ran, and stderr says why.
    match output.status.code() {
        Some(0 | 1) => {}
        _ => {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            if stderr.contains("unexpected argument '--fixture'") {
                return Err(Error::TooOld);
            }
            return Err(Error::Refused(stderr));
        }
    }
    let report: Value =
        serde_json::from_slice(&output.stdout).map_err(|e| Error::Report(e.to_string()))?;
    match report["report_version"].as_u64() {
        Some(REPORT_VERSION) => Ok(report),
        other => Err(Error::Report(format!(
            "version {other:?}; this crate reads version {REPORT_VERSION}"
        ))),
    }
}

/// A Streamform project directory: the models a fixture runs against.
#[derive(Debug, Clone)]
pub struct Project {
    path: PathBuf,
}

impl Project {
    /// Open the project at `path`.
    pub fn open(path: impl Into<PathBuf>) -> Result<Self, Error> {
        let path = path.into();
        if !path.join("streamform.yml").is_file() {
            return Err(Error::NotAProject(path));
        }
        Ok(Project { path })
    }

    /// The project's directory.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Start a fixture for `model`.
    pub fn fixture(&self, model: &str) -> Fixture {
        Fixture {
            project: self.path.clone(),
            model: model.to_string(),
            given: Vec::new(),
            expect: None,
            late: None,
            quarantined: None,
            owner: None,
        }
    }

    /// Run the project's own `tests/` fixtures and return the binary's test report.
    pub fn test(&self) -> Result<Value, Error> {
        run_binary(&["test", "--json"], &self.path, None)
    }
}

/// Run every fixture in the project's `tests/`, and panic with each problem
/// unless all pass: one `#[test]` that keeps `cargo test` and the fixtures together.
///
/// ```no_run
/// #[test]
/// fn fixtures() {
///     streamform_test::assert_project_passes(".");
/// }
/// ```
#[track_caller]
pub fn assert_project_passes(path: impl Into<PathBuf>) {
    let project = Project::open(path).unwrap_or_else(|e| panic!("{e}"));
    let report = project.test().unwrap_or_else(|e| panic!("{e}"));
    let mut failures = Vec::new();
    for fixture in report["fixtures"].as_array().into_iter().flatten() {
        if fixture["passed"].as_bool() == Some(true) {
            continue;
        }
        let mut lines = vec![format!("{} ({})", fixture["path"], fixture["model"])];
        if let Some(error) = fixture["error"].as_str() {
            lines.push(format!("  the simulator refused it: {error}"));
        }
        lines.extend(
            problems_in(fixture, &["rows", "late", "quarantined"]).map(|p| format!("  {p}")),
        );
        failures.push(lines.join("\n"));
    }
    if !failures.is_empty() {
        panic!(
            "{} fixture(s) failed:\n{}",
            failures.len(),
            failures.join("\n")
        );
    }
}

fn problems_in<'a>(fixture: &'a Value, sections: &'a [&str]) -> impl Iterator<Item = String> + 'a {
    sections.iter().flat_map(move |section| {
        fixture[*section]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(move |row| {
                row["problem"]
                    .as_str()
                    .map(|p| format!("{section}[{}]: {p}", row["index"]))
            })
    })
}

/// A fixture for one model: events and watermarks in, and optionally what must come out.
#[derive(Debug, Clone)]
pub struct Fixture {
    project: PathBuf,
    model: String,
    given: Vec<Value>,
    expect: Option<Vec<Value>>,
    late: Option<Vec<Value>>,
    quarantined: Option<Vec<Value>>,
    /// Keeps a `StreamSql` project on disk for as long as a fixture uses it.
    owner: Option<std::sync::Arc<sql::TempProject>>,
}

impl Fixture {
    /// The project directory the fixture runs against.
    pub fn project_path(&self) -> &Path {
        &self.project
    }

    /// Deliver one event (a JSON object of column values) to the model's source.
    pub fn event(mut self, row: Value) -> Self {
        self.given.push(json!({ "event": row }));
        self
    }

    /// Deliver several events, in order.
    pub fn events(mut self, rows: impl IntoIterator<Item = Value>) -> Self {
        for row in rows {
            self = self.event(row);
        }
        self
    }

    /// Advance the source's watermark to `at`, an RFC 3339 instant; only on an event-time source.
    pub fn watermark(mut self, at: &str) -> Self {
        self.given.push(json!({ "watermark": at }));
        self
    }

    /// The exact changelog: each change is `op` plus every output column. The binary compares it.
    pub fn expect(mut self, changes: impl IntoIterator<Item = Value>) -> Self {
        self.expect = Some(changes.into_iter().collect());
        self
    }

    /// The events that must be dropped as late, in order. The binary compares them.
    pub fn expect_late(mut self, rows: impl IntoIterator<Item = Value>) -> Self {
        self.late = Some(rows.into_iter().collect());
        self
    }

    /// The events that must break a contract, each with `_contract`. The binary compares them.
    pub fn expect_quarantined(mut self, rows: impl IntoIterator<Item = Value>) -> Self {
        self.quarantined = Some(rows.into_iter().collect());
        self
    }

    /// The fixture document, as a `tests/*.yml` file would hold it.
    pub fn to_document(&self) -> Value {
        // An empty list asserts nothing here: the report still carries the
        // whole changelog, and the Run asserts only what this fixture named.
        json!({
            "model": self.model,
            "given": self.given,
            "expect": self.expect.clone().unwrap_or_default(),
            "late": self.late.clone().unwrap_or_default(),
            "quarantined": self.quarantined.clone().unwrap_or_default(),
        })
    }

    /// The fixture as JSON, which the binary reads as YAML.
    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(&self.to_document()).expect("a fixture serializes")
    }

    /// Save the fixture as a file, e.g. into the project's `tests/` to keep it.
    pub fn write(&self, path: impl AsRef<Path>) -> std::io::Result<()> {
        std::fs::write(path, self.to_json() + "\n")
    }

    /// Run the fixture through the simulator, in the binary.
    pub fn run(&self) -> Result<Run, Error> {
        let report = run_binary(
            &["test", "--json", "--fixture", "-"],
            &self.project,
            Some(&self.to_json()),
        )?;
        let entry = report["fixtures"][0].clone();
        if let Some(error) = entry["error"].as_str() {
            return Err(Error::Refused(format!(
                "the simulator refused the fixture: {error}"
            )));
        }
        Ok(Run::from_entry(
            entry,
            [
                self.expect.is_some(),
                self.late.is_some(),
                self.quarantined.is_some(),
            ],
        ))
    }
}

/// One record of the model's changelog.
#[derive(Debug, Clone, PartialEq)]
pub struct Change {
    /// `insert`, `update`, or `delete`.
    pub op: String,
    /// The row, or the after-image of an update, as the binary renders it.
    pub columns: Map<String, Value>,
    /// The row as it was, on an update.
    pub before: Option<Map<String, Value>>,
}

impl Change {
    /// Whether `expected` (`op` plus every column) describes this change.
    pub fn matches(&self, expected: &Value) -> bool {
        let Some(wanted) = expected.as_object() else {
            return false;
        };
        let mut columns = wanted.clone();
        let op = columns.remove("op");
        op.as_ref().and_then(Value::as_str) == Some(self.op.as_str())
            && same_row(&columns, &self.columns)
    }
}

impl fmt::Display for Change {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.op)?;
        for (name, value) in &self.columns {
            write!(f, " {name}={value}")?;
        }
        Ok(())
    }
}

/// A key's values, in the order of the key's columns.
pub type Key = Vec<Value>;

fn key_of(columns: &Map<String, Value>, key: &[&str]) -> Key {
    key.iter()
        .map(|k| {
            columns
                .get(*k)
                .cloned()
                .unwrap_or_else(|| panic!("the rows have no column `{k}`"))
        })
        .collect()
}

fn same_key(a: &Key, b: &Key) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x, y)| same(x, y))
}

/// One fixture, run through the simulator.
#[derive(Debug, Clone)]
pub struct Run {
    /// The fixture's entry of the binary's test report, unchanged.
    pub report: Value,
    /// Every record the model emitted, in order.
    pub changelog: Vec<Change>,
    /// The events dropped as late, as delivered, in order.
    pub late: Vec<Map<String, Value>>,
    /// The events that broke a contract, each with `_contract`, in order.
    pub quarantined: Vec<Map<String, Value>>,
    checks: [bool; 3],
}

const SECTIONS: [&str; 3] = ["rows", "late", "quarantined"];

impl Run {
    fn from_entry(report: Value, checks: [bool; 3]) -> Self {
        let actuals = |section: &str| -> Vec<Map<String, Value>> {
            report[section]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|row| row["actual"].as_object().cloned())
                .collect()
        };
        let changelog = actuals("rows")
            .into_iter()
            .map(|actual| Change {
                op: actual["op"].as_str().unwrap_or_default().to_string(),
                columns: actual["columns"].as_object().cloned().unwrap_or_default(),
                before: actual.get("before").and_then(Value::as_object).cloned(),
            })
            .collect();
        Run {
            changelog,
            late: actuals("late"),
            quarantined: actuals("quarantined"),
            report,
            checks,
        }
    }

    /// How many events the model's source received.
    pub fn events_processed(&self) -> u64 {
        self.report["events_processed"].as_u64().unwrap_or_default()
    }

    /// Every difference the binary found in what the fixture asserted.
    pub fn problems(&self) -> Vec<String> {
        let checked: Vec<&str> = SECTIONS
            .iter()
            .zip(self.checks)
            .filter_map(|(s, c)| c.then_some(*s))
            .collect();
        problems_in(&self.report, &checked).collect()
    }

    fn listing(&self) -> String {
        if self.changelog.is_empty() {
            return "  (nothing)".to_string();
        }
        self.changelog
            .iter()
            .enumerate()
            .map(|(i, c)| format!("  {}. {c}", i + 1))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Panic unless everything the fixture asserted held, listing each difference.
    #[track_caller]
    pub fn assert_passed(&self) -> &Self {
        let problems = self.problems();
        if !problems.is_empty() {
            panic!(
                "{} difference(s) from the fixture:\n  {}\n\nthe model emitted:\n{}",
                problems.len(),
                problems.join("\n  "),
                self.listing()
            );
        }
        self
    }

    /// Panic unless each expected change appears, in this order, among others.
    #[track_caller]
    pub fn assert_changelog_contains(&self, expected: &[Value]) -> &Self {
        let mut position = 0;
        for wanted in expected {
            while position < self.changelog.len() && !self.changelog[position].matches(wanted) {
                position += 1;
            }
            if position == self.changelog.len() {
                panic!("no change {wanted} in order in:\n{}", self.listing());
            }
            position += 1;
        }
        self
    }

    /// The changelog split per key, each key's changes in the order emitted.
    pub fn changes_by_key(&self, key: &[&str]) -> Vec<(Key, Vec<&Change>)> {
        let mut grouped: Vec<(Key, Vec<&Change>)> = Vec::new();
        for change in &self.changelog {
            let k = key_of(&change.columns, key);
            match grouped.iter_mut().find(|(g, _)| same_key(g, &k)) {
                Some((_, changes)) => changes.push(change),
                None => grouped.push((k, vec![change])),
            }
        }
        grouped
    }

    /// Panic unless each key's changes are exactly the expected ones for that
    /// key, in order. The order between keys is free.
    #[track_caller]
    pub fn assert_changelog_per_key(&self, key: &[&str], expected: &[Value]) -> &Self {
        let mut wanted: Vec<(Key, Vec<&Value>)> = Vec::new();
        for change in expected {
            let columns = change.as_object().cloned().unwrap_or_default();
            let k = key_of(&columns, key);
            match wanted.iter_mut().find(|(g, _)| same_key(g, &k)) {
                Some((_, changes)) => changes.push(change),
                None => wanted.push((k, vec![change])),
            }
        }
        let actual = self.changes_by_key(key);
        if wanted.len() != actual.len() {
            panic!(
                "expected changes for {} key(s), the model emitted for {}:\n{}",
                wanted.len(),
                actual.len(),
                self.listing()
            );
        }
        for (k, changes) in &wanted {
            let emitted = actual.iter().find(|(a, _)| same_key(a, k)).map(|(_, c)| c);
            let ok = emitted.is_some_and(|e| {
                e.len() == changes.len() && e.iter().zip(changes).all(|(c, w)| c.matches(w))
            });
            if !ok {
                panic!("key {k:?}: expected {changes:?}, got {emitted:?}");
            }
        }
        self
    }

    /// The table a keyed consumer holds after every change: each key's last row, deletes removed.
    pub fn final_state(&self, key: &[&str]) -> Vec<(Key, Map<String, Value>)> {
        self.changes_by_key(key)
            .into_iter()
            .filter_map(|(k, changes)| {
                let last = changes.last().expect("a key has a change");
                (last.op != "delete").then(|| (k, last.columns.clone()))
            })
            .collect()
    }

    /// Panic unless the final state per key is exactly these rows, in any order.
    #[track_caller]
    pub fn assert_final_state(&self, key: &[&str], rows: &[Value]) -> &Self {
        let state = self.final_state(key);
        let mut remaining: Vec<&(Key, Map<String, Value>)> = state.iter().collect();
        for row in rows {
            let columns = row.as_object().cloned().unwrap_or_default();
            let k = key_of(&columns, key);
            let found = remaining
                .iter()
                .position(|(a, held)| same_key(a, &k) && same_row(&columns, held));
            match found {
                Some(i) => {
                    remaining.remove(i);
                }
                None => panic!("final state has no row {row}; it holds {:?}", state),
            }
        }
        if !remaining.is_empty() {
            panic!("final state holds rows the test does not list: {remaining:?}");
        }
        self
    }

    /// Panic unless exactly these events were dropped as late, in order.
    #[track_caller]
    pub fn assert_late(&self, rows: &[Value]) -> &Self {
        assert_events("late", &self.late, rows);
        self
    }

    /// Panic unless exactly these events broke a contract, each with `_contract`, in order.
    #[track_caller]
    pub fn assert_quarantined(&self, rows: &[Value]) -> &Self {
        assert_events("quarantined", &self.quarantined, rows);
        self
    }
}

#[track_caller]
fn assert_events(what: &str, actual: &[Map<String, Value>], expected: &[Value]) {
    let ok = actual.len() == expected.len()
        && expected
            .iter()
            .zip(actual)
            .all(|(w, a)| w.as_object().is_some_and(|w| same_row(w, a)));
    if !ok {
        panic!("{what}: expected {expected:?}, got {actual:?}");
    }
}
