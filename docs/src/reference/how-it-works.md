# How it works

`streamform-test` does not run SQL itself. It is a small client of a streaming engine: Streamform's, the same one that compiles queries to Apache Flink for production.

```text
 your test                    streamform-test                 the engine (streamform)
 ─────────                    ───────────────                 ───────────────────────
 StreamSQL(sql, sources) ──►  writes a throwaway project
 .event(...).run()       ──►  writes the test as a fixture ─► streamform test --fixture - --json
                                                              compiles the query, runs every event
                                                              through a deterministic simulator
 run.assert_...(...)     ◄──  reads the report             ◄─ every change, late event, quarantined record
```

- **One process per run.** Each `.run()` starts the engine once; a run takes a few milliseconds.
- **Deterministic.** The simulator has no clock, no threads racing, no network: the same input gives the same changelog on every machine.
- **The same semantics as production.** Streamform runs its example applications both in the simulator and on a real Apache Flink cluster and compares the output event for event, so the simulator describes what Streamform runs on Flink.
- **Exact assertions are the engine's.** `expect`, `expect_late` and `expect_quarantined` are compared by the engine with its typed rules; the looser assertions read the changelog the engine reports.

## The engine package

`pip install streamform-test` installs `streamform-bin`, which carries the `streamform` binary for macOS (Apple silicon, Intel) and x86_64 Linux (a static build that runs on any distribution, Alpine included). The binary is free to use under its terms of use, included in that package. The Python package and the Rust crate are open source under Apache-2.0 and contain no engine code.

## Using it without Streamform

Nothing in `streamform-test` requires you to run Streamform in production. Use it to work out and pin down what a streaming query should do, wherever it will run. The results are Streamform's semantics: where another engine decides an edge case differently (hand-written Flink SQL, for one, still counts some events behind the watermark that Streamform drops as late), the test shows Streamform's answer. If you adopt Streamform later, [your tests move with you](../guides/streamform-projects.md).
