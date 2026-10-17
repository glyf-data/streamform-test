"""Finding and calling the `streamform` binary.

The library never contains the simulator: every run is `streamform test
--fixture - --json`, with the fixture on stdin and the test report on stdout.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

#: The environment variable that names the binary; otherwise `streamform` on PATH.
BINARY_ENV = "STREAMFORM_BIN"

#: The test report version this library reads (`report_version` in the report).
REPORT_VERSION = 1


class StreamformError(Exception):
    """The binary could not run a fixture: not found, too old, or the project or fixture is invalid."""


def find_binary() -> str:
    """The path of the `streamform` binary to run.

    `STREAMFORM_BIN` when set; else the binary `streamform-bin` installed
    beside this package; else `streamform` on PATH.
    """
    configured = os.environ.get(BINARY_ENV)
    if configured:
        return configured
    try:
        import streamform_bin
    except ImportError:
        pass
    else:
        bundled = streamform_bin.binary()
        if bundled.is_file():
            return str(bundled)
    found = shutil.which("streamform")
    if found is None:
        raise StreamformError(
            "no streamform binary: `pip install streamform-bin`, put streamform on PATH, "
            f"or set {BINARY_ENV} to the binary's path"
        )
    return found


def run_fixture(project: Path, fixture_json: str) -> dict[str, Any]:
    """Run one fixture through the binary and return its entry of the test report."""
    command = [find_binary(), "test", "--json", "--fixture", "-", "--project", str(project)]
    completed = subprocess.run(
        command, input=fixture_json, capture_output=True, text=True, check=False
    )
    # Exit 0: every assertion held. Exit 1: one failed, and the report says which.
    # Exit 2: nothing ran, and stderr says why.
    if completed.returncode not in (0, 1):
        stderr = completed.stderr.strip()
        if "--fixture" in stderr and "unexpected argument" in stderr:
            raise StreamformError(
                "this streamform cannot take a fixture from outside the project's tests/; "
                "streamform-test needs a streamform with `test --fixture` (0.9 or newer)"
            )
        raise StreamformError(stderr or f"streamform exited {completed.returncode}")
    report = json.loads(completed.stdout)
    if report.get("report_version") != REPORT_VERSION:
        raise StreamformError(
            f"streamform wrote test report version {report.get('report_version')}; "
            f"this library reads version {REPORT_VERSION}"
        )
    return report["fixtures"][0]


def run_project(project: Path, model: str | None = None) -> dict[str, Any]:
    """Run the project's own `tests/` and return the whole test report."""
    command = [find_binary(), "test", "--json", "--project", str(project)]
    if model is not None:
        command += ["--model", model]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode not in (0, 1):
        raise StreamformError(completed.stderr.strip() or f"streamform exited {completed.returncode}")
    return json.loads(completed.stdout)
