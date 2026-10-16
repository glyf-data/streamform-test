//! Bring your own SQL: test a streaming query without a Streamform project.
//!
//! `StreamSql` writes a throwaway project (one model, its sources) into a
//! temporary directory and runs fixtures against it, exactly as against a
//! project on disk. The query is a Streamform model: `source('name')` reads a
//! source, and the SQL is what Streamform supports.

use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{Map, Value, json};

use crate::{Error, Fixture, Project};

/// The fields of a source besides `schema`.
const SOURCE_FIELDS: [&str; 7] = [
    "schema",
    "event_time",
    "watermark",
    "late_events",
    "contracts",
    "quarantine",
    "key",
];

/// A project directory removed when the last fixture using it is dropped.
#[derive(Debug)]
pub(crate) struct TempProject {
    path: PathBuf,
}

impl Drop for TempProject {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}

fn unique_dir() -> std::io::Result<PathBuf> {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or_default();
    let path = std::env::temp_dir().join(format!(
        "streamform-sql-{}-{nanos}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::create_dir(&path)?;
    Ok(path)
}

/// A streaming SQL query under test, with the sources it reads.
///
/// ```no_run
/// use serde_json::json;
/// use streamform_test::StreamSql;
///
/// StreamSql::new("SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id")
///     .source("orders", json!({"customer_id": "int64", "amount": "decimal(12,2)"}))
///     .key(&["customer_id"])
///     .fixture().unwrap()
///     .event(json!({"customer_id": 42, "amount": 10}))
///     .run().unwrap()
///     .assert_final_state(&["customer_id"], &[json!({"customer_id": 42, "total": 10})]);
/// ```
#[derive(Debug, Clone)]
pub struct StreamSql {
    sql: String,
    model: String,
    sources: Map<String, Value>,
    config: Map<String, Value>,
    project: Option<Arc<TempProject>>,
}

impl StreamSql {
    /// A query; add its sources with [`StreamSql::source`].
    pub fn new(sql: &str) -> Self {
        let mut config = Map::new();
        config.insert("materialized".into(), json!("append"));
        StreamSql {
            sql: sql.trim().to_string(),
            model: "query".to_string(),
            sources: Map::new(),
            config,
            project: None,
        }
    }

    /// A source the query reads with `source('name')`: its column types as a
    /// JSON object, or a full source (`schema`, `event_time`, `watermark`,
    /// `late_events`, `contracts`, `quarantine`) as `sources.yml` holds it.
    pub fn source(mut self, name: &str, spec: Value) -> Self {
        let mut full = match spec {
            Value::Object(map) if map.contains_key("schema") => map,
            other => {
                let mut map = Map::new();
                map.insert("schema".into(), other);
                map
            }
        };
        if let Some(unknown) = full.keys().find(|k| !SOURCE_FIELDS.contains(&k.as_str())) {
            panic!("source `{name}`: unknown field `{unknown}`");
        }
        full.insert("connector".into(), json!("kafka"));
        full.insert("topic".into(), json!(name));
        full.entry("format").or_insert(json!("json"));
        self.sources.insert(name.into(), Value::Object(full));
        self.project = None;
        self
    }

    /// Make the result keyed (`materialized: upsert`), as an aggregate needs.
    pub fn key(mut self, columns: &[&str]) -> Self {
        self.config.insert("materialized".into(), json!("upsert"));
        self.config.insert("key".into(), json!(columns));
        self.project = None;
        self
    }

    /// Cut the result into tumbling windows of event time, such as `"5m"`.
    pub fn window(mut self, size: &str) -> Self {
        self.config
            .insert("window".into(), json!({"type": "tumbling", "size": size}));
        self.project = None;
        self
    }

    /// Name the model (default `query`), as error messages show it.
    pub fn model(mut self, name: &str) -> Self {
        self.model = name.to_string();
        self.project = None;
        self
    }

    fn write(&self) -> Result<Arc<TempProject>, Error> {
        if self.sources.is_empty() {
            return Err(Error::Refused("a query needs at least one source".into()));
        }
        let io =
            |e: std::io::Error| Error::Binary(format!("could not write the query's project: {e}"));
        let path = unique_dir().map_err(io)?;
        let project = Arc::new(TempProject { path: path.clone() });
        std::fs::create_dir(path.join("models")).map_err(io)?;
        std::fs::write(
            path.join(format!("models/{}.sql", self.model)),
            format!("{}\n", self.sql),
        )
        .map_err(io)?;
        // JSON is YAML, so the binary reads these files as written.
        let manifest =
            json!({"name": "streamsql", "version": 1, "models": {&self.model: self.config}});
        std::fs::write(path.join("streamform.yml"), manifest.to_string()).map_err(io)?;
        std::fs::write(
            path.join("sources.yml"),
            json!({"sources": self.sources}).to_string(),
        )
        .map_err(io)?;
        Ok(project)
    }

    /// Start a fixture for the query. The project is written on first use and
    /// removed when the query and every fixture from it are dropped.
    pub fn fixture(&mut self) -> Result<Fixture, Error> {
        let project = match &self.project {
            Some(project) => project.clone(),
            None => {
                let project = self.write()?;
                self.project = Some(project.clone());
                project
            }
        };
        let mut fixture = Project::open(project.path.clone())?.fixture(&self.model);
        fixture.owner = Some(project);
        Ok(fixture)
    }
}
