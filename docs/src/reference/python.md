# Python API

```python
from streamform_test import StreamSQL, Project, Fixture, Run, Change, Watermark, StreamformError
from streamform_test import events
```

## `StreamSQL(sql, *, sources, key=None, window=None, model="query")`

A query under test. `sources` maps names to column types or to full source definitions ([Testing a query](../guides/queries.md)). `key` (a column or a list) makes the result keyed; `window` (such as `"5m"`) adds tumbling windows.

| | |
|---|---|
| `.fixture()` | A new, empty `Fixture` for the query |
| `.event(...)`, `.events(rows)`, `.watermark(at)` | Start a `Fixture` with that input |
| `.path` | The temporary project the engine runs, removed with the object |

## `Project(path=".")`

A Streamform project directory.

| | |
|---|---|
| `.fixture(model)` | A new `Fixture` for one of the project's models |
| `.test(model=None)` | Run the project's `tests/*.yml`; returns the engine's test report |

## `Fixture`

Every method except `run`, `to_document`, `to_json` and `write` returns the fixture.

| | |
|---|---|
| `.event(row=None, /, **columns)` | One event, as a dict or keyword arguments |
| `.events(rows)` | Several events, in order |
| `.watermark(at)` | Move the watermark to an RFC 3339 instant or a `datetime` |
| `.feed(stream)` | A stream from `events`: dicts and `Watermark` items |
| `.expect(*changes)` | The exact changelog, compared by the engine |
| `.expect_late(*rows)` | The exact late events, compared by the engine |
| `.expect_quarantined(*rows)` | The exact quarantined records, compared by the engine |
| `.run()` | Run it; returns a `Run` |
| `.write(path)` | Save it as a fixture file |

## `Run`

| | |
|---|---|
| `.changelog` | `list[Change]`, every change in order |
| `.late` | Events dropped as late, as delivered |
| `.quarantined` | Records that broke a contract, each with `_contract` |
| `.events_processed` | How many events the source received |
| `.report` | The engine's report for this run, unchanged |
| `.problems()` | Differences from `expect`, `expect_late` and `expect_quarantined` |
| `.assert_passed()` | Fail on any of those differences |
| `.assert_changelog_contains(*changes)` | These changes, in order, among others |
| `.assert_changelog_per_key(key, *changes)` | Each key's changes exactly and in order |
| `.changes_by_key(key)` | `{key tuple: [Change, ...]}` |
| `.final_state(key)` | `{key tuple: row}`, each key's last row, deletes removed |
| `.assert_final_state(key, *rows)` | The final state is exactly these rows |
| `.assert_late(*rows)` | Exactly these late events, in order |
| `.assert_quarantined(*rows)` | Exactly these quarantined records, in order |

Every assertion returns the run, so they chain.

## `Change`

`op` (`"insert"`, `"update"`, `"delete"`), `columns` (the row, or the row after an update), `before` (the row before an update, else `None`).

## `events`

| | |
|---|---|
| `repeat(n, row_or_fn)` | `n` events; `fn(i)` for each index |
| `product(**columns)` | One event per combination of listed values |
| `timed(rows, *, column, start, every)` | Stamp event times in steps |
| `random_rows(n, *, seed=0, **columns)` | Generated events; generators below, plain values copied |
| `choice(values)`, `integers(low, high)`, `decimals(low, high, places=2)`, `sequence(start=1, step=1)`, `times(start, every, jitter=None)` | Generators |
| `read_csv(path, *, types=None)`, `read_jsonl(path)`, `write_jsonl(path, rows)` | Files |
| `merge(*streams, by)` | Interleave time-ordered streams by event time |
| `with_watermarks(rows, *, by, lag="0s", every=1)` | Add forward-only watermarks |
| `Watermark(at)` | A watermark item in a stream |
| `duration(text)`, `instant(value)`, `rfc3339(datetime)` | Helpers for times |

## `StreamformError`

The engine could not run a test: not installed, too old, or the query or input is invalid. Its message is the engine's.
