"""The pytest plugin: fixture files as tests, and a `streamform_project` fixture.

Installed with the package and loaded by pytest automatically:

- Every `tests/*.yml` beside a `streamform.yml`, inside the paths pytest
  collects, becomes one test item, run by the binary like `streamform test`.
- The `streamform_project` fixture is the project named by `--streamform-project`
  or the `streamform_project` ini option, defaulting to the root directory.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from . import Project, binary


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("streamform")
    group.addoption(
        "--streamform-project",
        default=None,
        help="the Streamform project directory the streamform_project fixture opens",
    )
    parser.addini(
        "streamform_project", "the Streamform project directory", default=None
    )


@pytest.fixture
def streamform_project(request: pytest.FixtureRequest) -> Project:
    """The Streamform project under test."""
    configured = request.config.getoption("--streamform-project") or request.config.getini(
        "streamform_project"
    )
    root = Path(str(request.config.rootpath))
    return Project(root / configured if configured else root)


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> pytest.Collector | None:
    if (
        file_path.suffix == ".yml"
        and file_path.parent.name == "tests"
        and (file_path.parent.parent / "streamform.yml").is_file()
    ):
        return FixtureFile.from_parent(parent, path=file_path)
    return None


class FixtureFile(pytest.File):
    def collect(self) -> Iterator[pytest.Item]:
        yield FixtureItem.from_parent(self, name=self.path.stem)


class FixtureItem(pytest.Item):
    def runtest(self) -> None:
        project = self.path.parent.parent
        entry = binary.run_fixture(project, self.path.read_text(encoding="utf-8"))
        if entry.get("error"):
            raise FixtureFailed([f"the simulator refused the fixture: {entry['error']}"])
        problems = [
            f"{section}[{row['index']}]: {row['problem']}"
            for section in ("rows", "late", "quarantined")
            for row in entry.get(section, [])
            if row.get("problem")
        ]
        if problems:
            raise FixtureFailed(problems)

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException], style: Any = None) -> str:
        if isinstance(excinfo.value, FixtureFailed):
            return "\n".join(excinfo.value.problems)
        return str(super().repr_failure(excinfo))

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.path, 0, f"fixture {self.name}"


class FixtureFailed(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems
