"""Comparing a value a test wrote with a value the binary reported.

The binary renders values after typing them against the model's output
schema: decimals as exact strings (`"28"`), timestamps as RFC 3339 with
milliseconds (`"2026-08-30T10:00:00.000Z"`), integers and booleans as
themselves. A test writes `28`, `28.0`, or `"2026-08-30T10:00:00Z"`. These
rules make the two compare equal when they mean the same value, and nothing
else.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _as_instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and "T" in value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def same(expected: Any, actual: Any) -> bool:
    """Whether `expected`, as a test wrote it, means the value `actual` the binary reported."""
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    left, right = _as_decimal(expected), _as_decimal(actual)
    if left is not None and right is not None:
        return left == right
    left_t, right_t = _as_instant(expected), _as_instant(actual)
    if left_t is not None and right_t is not None:
        return left_t == right_t
    return expected == actual


def same_row(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Whether every column the test names has the value the binary reported, and no more columns exist."""
    return expected.keys() == actual.keys() and all(
        same(value, actual[name]) for name, value in expected.items()
    )


def for_fixture(value: Any) -> Any:
    """A value as a fixture file carries it (JSON, which the binary reads as YAML)."""
    if isinstance(value, datetime):
        instant = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value
