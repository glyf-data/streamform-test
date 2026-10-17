"""Building event streams: loops, generators, files, and merging by event time.

Every function returns a plain list, so streams compose with Python itself::

    from streamform_test import events as ev

    orders = ev.timed(ev.repeat(3, lambda i: {"customer_id": 42, "amount": 10 * (i + 1)}),
                      column="ordered_at", start="2026-08-30T10:00:00Z", every="1m")
    refunds = ev.read_jsonl("refunds.jsonl")
    stream = ev.with_watermarks(ev.merge(orders, refunds, by="ordered_at"),
                                by="ordered_at", lag="1m")
    run = project.fixture("spend_per_5m").feed(stream).run()

A stream is a list of items: an event is a dict of column values, and a
`Watermark` advances the source's watermark between events.
"""

from __future__ import annotations

import csv
import heapq
import itertools
import json
import random as _random
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

Row = dict[str, Any]


@dataclass(frozen=True)
class Watermark:
    """An item of a stream that advances the source's watermark to `at`."""

    at: datetime | str


Item = Row | Watermark

# Durations as Streamform writes them: 500ms, 30s, 5m, 2h, 7d.
_DURATION = re.compile(r"^(\d+)(ms|s|m|h|d)$")
_UNITS = {"ms": "milliseconds", "s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def duration(text: str | timedelta) -> timedelta:
    """`"500ms"`, `"30s"`, `"5m"`, `"2h"` or `"7d"` as a timedelta."""
    if isinstance(text, timedelta):
        return text
    match = _DURATION.match(text.strip())
    if match is None:
        raise ValueError(f"not a duration: {text!r}; write it like 500ms, 30s, 5m, 2h or 7d")
    return timedelta(**{_UNITS[match[2]]: int(match[1])})


def instant(value: datetime | str) -> datetime:
    """An RFC 3339 instant (or a datetime) as an aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def rfc3339(value: datetime) -> str:
    """A datetime as the RFC 3339 text fixtures use, in UTC, with milliseconds when not whole."""
    value = instant(value)
    text = value.strftime("%Y-%m-%dT%H:%M:%S")
    if value.microsecond:
        text += f".{value.microsecond // 1000:03d}"
    return text + "Z"


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------


def repeat(n: int, row: Mapping[str, Any] | Callable[[int], Mapping[str, Any]]) -> list[Row]:
    """`n` events: the same row each time, or `row(i)` for i in 0..n."""
    if callable(row):
        return [dict(row(i)) for i in range(n)]
    return [dict(row) for _ in range(n)]


def product(**columns: Any) -> list[Row]:
    """One event per combination of the listed values; a scalar is the same in every event.

    `product(customer_id=[1, 2], amount=[5, 10])` is four events.
    """
    names = list(columns)
    choices = [v if isinstance(v, (list, tuple, range)) else [v] for v in columns.values()]
    return [dict(zip(names, combo)) for combo in itertools.product(*choices)]


def timed(
    rows: Iterable[Mapping[str, Any]],
    *,
    column: str,
    start: datetime | str,
    every: str | timedelta,
) -> list[Row]:
    """The rows with `column` set to `start`, `start + every`, `start + 2 * every`, and so on."""
    first, step = instant(start), duration(every)
    return [{**row, column: rfc3339(first + i * step)} for i, row in enumerate(rows)]


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


Generator = Callable[[_random.Random, int], Any]


def choice(values: Sequence[Any]) -> Generator:
    """Pick one of `values` for each event."""
    return lambda rng, _i: rng.choice(list(values))


def integers(low: int, high: int) -> Generator:
    """A whole number from `low` to `high`, both included."""
    return lambda rng, _i: rng.randint(low, high)


def decimals(low: float | str, high: float | str, places: int = 2) -> Generator:
    """An exact decimal from `low` to `high` with `places` fractional digits."""
    scale = 10**places
    lo, hi = int(Decimal(str(low)) * scale), int(Decimal(str(high)) * scale)
    return lambda rng, _i: Decimal(rng.randint(lo, hi)) / scale


def sequence(start: int = 1, step: int = 1) -> Generator:
    """`start`, `start + step`, ... in event order: ids that never repeat."""
    return lambda _rng, i: start + i * step


def times(start: datetime | str, every: str | timedelta, jitter: str | timedelta | None = None) -> Generator:
    """Event time stepping by `every`, each moved up to `jitter` earlier or later: out-of-order arrival."""
    first, step = instant(start), duration(every)
    spread = duration(jitter).total_seconds() if jitter else 0.0

    def make(rng: _random.Random, i: int) -> str:
        shift = timedelta(seconds=rng.uniform(-spread, spread)) if spread else timedelta()
        return rfc3339(first + i * step + shift)

    return make


def random_rows(n: int, *, seed: int = 0, **columns: Generator | Any) -> list[Row]:
    """`n` events with each column drawn from its generator; a plain value is the same in every event.

    The same `seed` gives the same events on every run, so a failing test fails again.
    """
    rng = _random.Random(seed)
    return [
        {name: (make(rng, i) if callable(make) else make) for name, make in columns.items()}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def _auto(text: str) -> Any:
    """A CSV cell as the value a fixture would hold: empty is null, numbers are numbers."""
    if text == "":
        return None
    if text in ("true", "false"):
        return text == "true"
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    try:
        if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+)", text):
            return Decimal(text)
    except InvalidOperation:
        pass
    return text


def read_csv(
    path: str | Path,
    *,
    types: Mapping[str, Callable[[str], Any]] | None = None,
) -> list[Row]:
    """Events from a CSV file with a header row.

    Cells are read as a fixture would hold them: empty is null, `true`/`false`
    are booleans, whole numbers are integers, other numbers exact decimals,
    anything else a string. `types` overrides a column, e.g. `{"zip": str}`
    for a string column of digits.
    """
    overrides = dict(types or {})
    with open(path, newline="", encoding="utf-8") as handle:
        return [
            {
                name: (overrides[name](cell) if name in overrides else _auto(cell))
                for name, cell in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def read_jsonl(path: str | Path) -> list[Row]:
    """Events from a JSON Lines file, one object per line; decimals keep their exact digits."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if line.strip():
                value = json.loads(line, parse_float=Decimal)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{number}: expected a JSON object per line")
                rows.append(value)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    """Save events as JSON Lines, to keep a generated stream beside the tests."""
    target = Path(path)
    with open(target, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")
    return target


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def merge(*streams: Iterable[Mapping[str, Any]], by: str) -> list[Row]:
    """One stream of every event, ordered by the event-time column `by`.

    Each stream must already be in `by` order; events with the same time keep
    the order of the streams as given. Watermark items are not allowed here:
    add them after merging, with `with_watermarks`.
    """
    def keyed(index: int, stream: Iterable[Mapping[str, Any]]):
        last = None
        for position, row in enumerate(stream):
            if isinstance(row, Watermark):
                raise ValueError("merge takes events only; add watermarks after merging")
            at = instant(row[by])
            if last is not None and at < last:
                raise ValueError(f"stream {index} is not in `{by}` order at event {position}")
            last = at
            yield (at, index, position, dict(row))

    return [row for *_, row in heapq.merge(*(keyed(i, s) for i, s in enumerate(streams)))]


def with_watermarks(
    rows: Iterable[Mapping[str, Any]],
    *,
    by: str,
    lag: str | timedelta = "0s",
    every: int = 1,
) -> list[Item]:
    """The events with a `Watermark` after every `every` events, at the latest event time seen minus `lag`.

    A watermark is added only when it moves forward, as a real source's does.
    Events behind it afterwards are late: a source with `late_events: drop`
    drops them, and the run reports them.
    """
    back = duration(lag)
    out: list[Item] = []
    newest: datetime | None = None
    current: datetime | None = None
    for count, row in enumerate(rows, start=1):
        out.append(dict(row))
        at = instant(row[by])
        newest = at if newest is None or at > newest else newest
        if count % every == 0 and (current is None or newest - back > current):
            current = newest - back
            out.append(Watermark(rfc3339(current)))
    return out
