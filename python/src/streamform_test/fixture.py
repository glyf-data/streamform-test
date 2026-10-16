"""Building a fixture in code: the same document as a `tests/*.yml` file."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from collections.abc import Iterable, Mapping
from typing import Any

from . import binary
from .run import Run
from .values import for_fixture

Row = Mapping[str, Any]


def _dump(value: Any) -> str:
    """JSON text for a fixture value; a Decimal is written as the exact number it is."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{json.dumps(str(k))}: {_dump(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_dump(v) for v in value) + "]"
    return json.dumps(for_fixture(value))


class Fixture:
    """A fixture for one model: events and watermarks in, and optionally what must come out.

    Every method returns the fixture, so a test reads top to bottom::

        run = (project.fixture("spend_per_5m")
               .event(customer_id=42, amount=60, ordered_at="2026-08-30T10:01:00Z")
               .watermark("2026-08-30T10:05:00Z")
               .run())
    """

    def __init__(self, project: Path, model: str) -> None:
        self._project = project
        self.model = model
        self.given: list[dict[str, Any]] = []
        self.expected: list[dict[str, Any]] | None = None
        self.late: list[dict[str, Any]] | None = None
        self.quarantined: list[dict[str, Any]] | None = None

    def event(self, row: Row | None = None, /, **columns: Any) -> Fixture:
        """Deliver one event to the model's source: a row, or its columns as keywords."""
        self.given.append({"event": {**(row or {}), **columns}})
        return self

    def events(self, rows: Iterable[Row]) -> Fixture:
        """Deliver several events, in order."""
        for row in rows:
            self.event(row)
        return self

    def watermark(self, at: str | datetime) -> Fixture:
        """Advance the source's watermark to `at` (never backwards); only on an event-time source."""
        self.given.append({"watermark": at})
        return self

    def expect(self, *changes: Row) -> Fixture:
        """The exact changelog: each change is `op` plus every output column. The binary compares it."""
        self.expected = [dict(change) for change in changes]
        return self

    def expect_late(self, *rows: Row) -> Fixture:
        """The events that must be dropped as late, as delivered, in order. The binary compares them."""
        self.late = [dict(row) for row in rows]
        return self

    def expect_quarantined(self, *rows: Row) -> Fixture:
        """The events that must break a contract, each with `_contract`. The binary compares them."""
        self.quarantined = [dict(row) for row in rows]
        return self

    def to_document(self) -> dict[str, Any]:
        """The fixture document, as a `tests/*.yml` file would hold it."""
        return {
            "model": self.model,
            "given": self.given,
            # An empty list asserts nothing here: the report still carries the
            # whole changelog, and the Run asserts only what this fixture named.
            "expect": self.expected or [],
            "late": self.late or [],
            "quarantined": self.quarantined or [],
        }

    def to_json(self) -> str:
        """The fixture as JSON, which the binary reads as YAML."""
        return _dump(self.to_document())

    def write(self, path: str | Path) -> Path:
        """Save the fixture as a file, e.g. into the project's `tests/` to keep it."""
        target = Path(path)
        target.write_text(self.to_json() + "\n", encoding="utf-8")
        return target

    def run(self) -> Run:
        """Run the fixture through the simulator, in the binary."""
        entry = binary.run_fixture(self._project, self.to_json())
        return Run(
            entry,
            checks_changelog=self.expected is not None,
            checks_late=self.late is not None,
            checks_quarantined=self.quarantined is not None,
        )
