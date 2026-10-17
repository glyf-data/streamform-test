# Contributing

## The repository

| | |
|---|---|
| [`python/`](python/) | The Python package, Python 3.13 or newer |
| [`rust/`](rust/) | The Rust crate |
| [`examples/`](examples/README.md) | A runnable test for every kind of check, in Python and Rust |
| [`docs/`](docs/src/introduction.md) | The documentation, as an mdBook |
| [`testdata/`](testdata/) | Example projects the library's own tests use |

## Developing

The tests need a `streamform` binary, version 0.9 or newer. `pip install streamform` gives you one, or point `STREAMFORM_BIN` at a binary you have.

```bash
cd python && uv venv -p 3.13 && uv pip install -e '.[pytest]' && .venv/bin/python -m pytest
cd rust && cargo test && cargo clippy --all-targets -- -D warnings
cd examples && ../python/.venv/bin/python -m pytest && (cd rust && cargo test)
mdbook build docs                              # the documentation, into docs/book/
```

## Releasing

Set the same version in `python/pyproject.toml`, `python/src/streamform_test/__init__.py` and `rust/Cargo.toml`, then push a `v<version>` tag. The release workflow checks that the versions match the tag, builds the package, installs it from scratch (which brings the `streamform` binary from PyPI) and runs the tests, then creates a GitHub release and publishes to PyPI through trusted publishing. Running it by hand with `publish_to_testpypi` is a dry run against TestPyPI.

The `streamform` package is published by Streamform's own release, so a new engine needs no release here.

```bash
git tag v0.1.0 && git push origin v0.1.0
(cd rust && cargo publish)              # the crate is published by hand
```
