"""What one fixture run produced, and assertions over it."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .values import same, same_row


@dataclass(frozen=True)
class Change:
    """One record of the model's changelog."""

    op: str
    """`insert`, `update`, or `delete`."""
    columns: dict[str, Any]
    """The row, or the after-image of an update, rendered as the binary types it."""
    before: dict[str, Any] | None = None
    """The row as it was, on an update."""

    def matches(self, expected: Mapping[str, Any]) -> bool:
        """Whether `expected` (`op` plus every column) describes this change."""
        wanted = dict(expected)
        op = wanted.pop("op", None)
        return op == self.op and same_row(wanted, self.columns)

    def __str__(self) -> str:
        values = " ".join(f"{k}={v}" for k, v in self.columns.items())
        return f"{self.op} {values}"


def _key_of(columns: Mapping[str, Any], key: Sequence[str]) -> tuple[Any, ...]:
    missing = [k for k in key if k not in columns]
    if missing:
        raise KeyError(f"the model's rows have no column {', '.join(missing)}")
    return tuple(columns[k] for k in key)


def _keys(key: str | Sequence[str]) -> list[str]:
    return [key] if isinstance(key, str) else list(key)


class Run:
    """One fixture, run through the simulator."""

    def __init__(
        self,
        entry: Mapping[str, Any],
        *,
        checks_changelog: bool,
        checks_late: bool,
        checks_quarantined: bool,
    ) -> None:
        self.report: Mapping[str, Any] = entry
        """The fixture's entry of the binary's test report, unchanged."""
        if entry.get("error"):
            raise AssertionError(f"the simulator refused the fixture: {entry['error']}")
        self.changelog: list[Change] = [
            Change(r["actual"]["op"], dict(r["actual"]["columns"]), r["actual"].get("before"))
            for r in entry.get("rows", [])
            if r.get("actual")
        ]
        """Every record the model emitted, in order."""
        self.late: list[dict[str, Any]] = [
            dict(r["actual"]) for r in entry.get("late", []) if r.get("actual")
        ]
        """The events dropped as late, as delivered, in order."""
        self.quarantined: list[dict[str, Any]] = [
            dict(r["actual"]) for r in entry.get("quarantined", []) if r.get("actual")
        ]
        """The events that broke a contract, each with `_contract`, in order."""
        self._checks = {
            "rows": checks_changelog,
            "late": checks_late,
            "quarantined": checks_quarantined,
        }

    @property
    def events_processed(self) -> int:
        return int(self.report["events_processed"])

    def problems(self) -> list[str]:
        """Every difference the binary found in what the fixture asserted (`expect`, `expect_late`, ...)."""
        found = []
        for section, checked in self._checks.items():
            if not checked:
                continue
            for row in self.report.get(section, []):
                if row.get("problem"):
                    found.append(f"{section}[{row['index']}]: {row['problem']}")
        return found

    def assert_passed(self) -> Run:
        """Fail unless everything the fixture asserted held, listing each difference."""
        problems = self.problems()
        if problems:
            listing = "\n".join(f"  {p}" for p in problems)
            actual = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(self.changelog))
            raise AssertionError(
                f"{len(problems)} difference(s) from the fixture:\n{listing}\n\nthe model emitted:\n{actual}"
            )
        return self

    def assert_changelog_contains(self, *expected: Mapping[str, Any]) -> Run:
        """Fail unless each expected change (`op` plus every column) appears, in this order, among others."""
        position = 0
        for wanted in expected:
            while position < len(self.changelog) and not self.changelog[position].matches(wanted):
                position += 1
            if position == len(self.changelog):
                raise AssertionError(f"no change {dict(wanted)} in order in:\n{self._listing()}")
            position += 1
        return self

    def changes_by_key(self, key: str | Sequence[str]) -> dict[tuple[Any, ...], list[Change]]:
        """The changelog split per key, each key's changes in the order emitted."""
        names = _keys(key)
        grouped: dict[tuple[Any, ...], list[Change]] = {}
        for change in self.changelog:
            grouped.setdefault(_key_of(change.columns, names), []).append(change)
        return grouped

    def assert_changelog_per_key(
        self, key: str | Sequence[str], *expected: Mapping[str, Any]
    ) -> Run:
        """Fail unless each key's changes are exactly the expected ones for that key, in order.

        The order between keys is free: what a topic keyed by `key` guarantees.
        """
        names = _keys(key)
        wanted: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
        for change in expected:
            columns = {k: v for k, v in change.items() if k != "op"}
            wanted.setdefault(_key_of(columns, names), []).append(change)
        actual = self.changes_by_key(names)
        if len(wanted) != len(actual):
            raise AssertionError(
                f"expected changes for {len(wanted)} key(s), the model emitted for {len(actual)}:\n{self._listing()}"
            )
        for k, changes in wanted.items():
            emitted = next((v for ak, v in actual.items() if _same_key(k, ak)), None)
            if emitted is None or len(emitted) != len(changes) or not all(
                c.matches(w) for c, w in zip(emitted, changes)
            ):
                got = "\n".join(f"  {c}" for c in emitted or [])
                raise AssertionError(f"key {k}: expected {list(map(dict, changes))}, got:\n{got}")
        return self

    def final_state(self, key: str | Sequence[str]) -> dict[tuple[Any, ...], dict[str, Any]]:
        """The table a keyed consumer holds after every change: each key's last row, deletes removed."""
        state: dict[tuple[Any, ...], dict[str, Any]] = {}
        for k, changes in self.changes_by_key(key).items():
            last = changes[-1]
            if last.op != "delete":
                state[k] = last.columns
        return state

    def assert_final_state(self, key: str | Sequence[str], *rows: Mapping[str, Any]) -> Run:
        """Fail unless the final state per key is exactly these rows, in any order."""
        names = _keys(key)
        state = self.final_state(names)
        remaining = dict(state)
        for row in rows:
            k = _key_of(row, names)
            match = next((ak for ak in remaining if _same_key(k, ak)), None)
            if match is None or not same_row(dict(row), remaining[match]):
                raise AssertionError(
                    f"final state has no row {dict(row)}; it holds:\n"
                    + "\n".join(f"  {v}" for v in state.values())
                )
            del remaining[match]
        if remaining:
            raise AssertionError(
                "final state holds rows the test does not list:\n"
                + "\n".join(f"  {v}" for v in remaining.values())
            )
        return self

    def assert_late(self, *rows: Mapping[str, Any]) -> Run:
        """Fail unless exactly these events were dropped as late, in order."""
        return self._assert_events("late", self.late, rows)

    def assert_quarantined(self, *rows: Mapping[str, Any]) -> Run:
        """Fail unless exactly these events broke a contract, each with `_contract`, in order."""
        return self._assert_events("quarantined", self.quarantined, rows)

    def _assert_events(
        self, what: str, actual: list[dict[str, Any]], expected: Iterable[Mapping[str, Any]]
    ) -> Run:
        wanted = [dict(r) for r in expected]
        if len(wanted) != len(actual) or not all(same_row(w, a) for w, a in zip(wanted, actual)):
            raise AssertionError(f"{what}: expected {wanted}, got {actual}")
        return self

    def _listing(self) -> str:
        return "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(self.changelog)) or "  (nothing)"


def _same_key(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
    return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
