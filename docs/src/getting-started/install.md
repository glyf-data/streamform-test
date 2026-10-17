# Install

## Python

Python 3.13 or newer.

```bash
pip install streamform-test
```

On macOS (Apple silicon and Intel) and x86_64 Linux, glibc or musl, this also installs `streamform`, the engine, and its `streamform` command. There is nothing else to set up.

On other platforms, install the `streamform` binary yourself and put it on `PATH`, or point `STREAMFORM_BIN` at it.

The library looks for the engine in this order:

1. `STREAMFORM_BIN`, when set.
2. The binary from the `streamform` package.
3. `streamform` on `PATH`.

It needs `streamform` 0.9 or newer. An older one gets an error naming the version needed, never a wrong result.

## Rust

```toml
# Cargo.toml
[dev-dependencies]
streamform-test = { git = "https://github.com/glyf-data/streamform-test", tag = "v0.1.0" }
serde_json = "1"
```

The crate finds the engine through `STREAMFORM_BIN` or `streamform` on `PATH`. The simplest way to get it is `pip install streamform`, which puts `streamform` on the environment's `PATH`.

## Check it works

```bash
python -c "from streamform_test import StreamSQL; print(StreamSQL('SELECT * FROM source(\'s\')', sources={'s': {'x': 'int64'}}).event(x=1).run().changelog)"
```

```text
[Change(op='insert', columns={'x': 1}, before=None)]
```
