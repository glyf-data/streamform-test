"""Bring your own SQL: test a streaming query without a Streamform project.

`StreamSQL` writes a throwaway project (one model, its sources) into a
temporary directory and runs fixtures against it, exactly as against a
project on disk. The query is a Streamform model: `source('name')` reads a
source, and the SQL is what Streamform supports.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import weakref
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .fixture import Fixture

#: The fields of a source besides `schema`; anything else is a column type map.
SOURCE_FIELDS = {"schema", "event_time", "watermark", "late_events", "contracts", "quarantine", "key"}


def _source(name: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    full = dict(spec) if "schema" in spec else {"schema": dict(spec)}
    unknown = set(full) - SOURCE_FIELDS
    if unknown:
        raise ValueError(f"source `{name}`: unknown field(s) {', '.join(sorted(unknown))}")
    return {"connector": "kafka", "topic": name, "format": "json", **full}


class StreamSQL:
    """A streaming SQL query under test, with the sources it reads.

    ::

        totals = StreamSQL(
            "SELECT customer_id, SUM(amount) AS total FROM source('orders') GROUP BY customer_id",
            sources={"orders": {"customer_id": "int64", "amount": "decimal(12,2)"}},
            key=["customer_id"],
        )
        totals.event(customer_id=42, amount=10).event(customer_id=42, amount=5).run() \\
              .assert_final_state("customer_id", {"customer_id": 42, "total": 15})

    `sources` maps each source to its column types, or to a full source
    (`schema`, `event_time`, `watermark`, `late_events`, `contracts`,
    `quarantine`) as `sources.yml` holds it. `key` makes the result keyed
    (`materialized: upsert`), as an aggregate needs; `window` cuts it into
    tumbling windows of event time, such as `"5m"`.
    """

    def __init__(
        self,
        sql: str,
        *,
        sources: Mapping[str, Mapping[str, Any]],
        key: str | Sequence[str] | None = None,
        window: str | None = None,
        model: str = "query",
    ) -> None:
        if not sources:
            raise ValueError("a query needs at least one source")
        self.sql = sql
        self.model = model
        self._sources = {name: _source(name, spec) for name, spec in sources.items()}
        config: dict[str, Any] = {"materialized": "append"}
        if key is not None:
            config = {"materialized": "upsert", "key": [key] if isinstance(key, str) else list(key)}
        if window is not None:
            config["window"] = {"type": "tumbling", "size": window}
        self._config = config
        self._path: Path | None = None

    @property
    def path(self) -> Path:
        """The throwaway project, written on first use and removed with this object."""
        if self._path is None:
            path = Path(tempfile.mkdtemp(prefix="streamform-sql-"))
            (path / "models").mkdir()
            (path / "models" / f"{self.model}.sql").write_text(self.sql.strip() + "\n", encoding="utf-8")
            # JSON is YAML, so the binary reads these files as written.
            manifest = {"name": "streamsql", "version": 1, "models": {self.model: self._config}}
            (path / "streamform.yml").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            (path / "sources.yml").write_text(
                json.dumps({"sources": self._sources}, indent=2), encoding="utf-8"
            )
            weakref.finalize(self, shutil.rmtree, path, True)
            self._path = path
        return self._path

    def fixture(self) -> Fixture:
        """Start a fixture for the query."""
        fixture = Fixture(self.path, self.model)
        # The fixture keeps the query alive: `StreamSQL(...).event(...).run()`
        # must not remove the project between the two calls.
        fixture._owner = self
        return fixture

    def event(self, row: Mapping[str, Any] | None = None, /, **columns: Any) -> Fixture:
        """Start a fixture with one event; see `Fixture.event`."""
        return self.fixture().event(row, **columns)

    def events(self, rows: Sequence[Mapping[str, Any]]) -> Fixture:
        """Start a fixture with several events."""
        return self.fixture().events(rows)

    def watermark(self, at: Any) -> Fixture:
        """Start a fixture with a watermark."""
        return self.fixture().watermark(at)
