"""streamform-test: write streaming tests in Python, run them in the free `streamform` binary.

The library builds fixtures, runs them with `streamform test --fixture - --json`,
and asserts on the report. It never contains the simulator or the compiler.
"""

from pathlib import Path
from typing import Any

from . import binary, events
from .binary import StreamformError
from .events import Watermark
from .fixture import Fixture
from .run import Change, Run
from .sql import StreamSQL

__all__ = ["Change", "Fixture", "Project", "Run", "StreamSQL", "StreamformError", "Watermark", "events"]
__version__ = "0.1.0"


class Project:
    """A Streamform project directory: the models a fixture runs against."""

    def __init__(self, path: str | Path = ".") -> None:
        self.path = Path(path)
        if not (self.path / "streamform.yml").is_file():
            raise StreamformError(f"{self.path} is not a Streamform project: no streamform.yml")

    def fixture(self, model: str) -> Fixture:
        """Start a fixture for `model`."""
        return Fixture(self.path, model)

    def test(self, model: str | None = None) -> dict[str, Any]:
        """Run the project's own `tests/` fixtures and return the binary's test report."""
        return binary.run_project(self.path, model)
