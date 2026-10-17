"""Build the `streamform-bin` wheels from a Streamform release's assets.

    python bin/build_wheels.py --assets DIR --version 0.9.0 --out dist/

DIR holds a release's `checksums.txt`, `LICENSE` (the terms of use) and the
`streamform-<target>.tar.gz` archives. Every archive is checked against
`checksums.txt` before its binary goes into a wheel; a mismatch stops the build.

Each wheel holds the binary once, inside the package, where
`streamform_bin.binary()` finds it, and installs a `streamform` command (an
entry point that replaces itself with the binary). The wheel holds no source.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import stat
import tarfile
import zipfile
from pathlib import Path

NAME = "streamform_bin"
DIST = "streamform-bin"

# Release target -> wheel platform tag. The tags state what the binaries need:
# macOS 10.12 (x86_64) and 11.0 (arm64), as their LC_BUILD_VERSION says, and
# glibc 2.39 for the Linux build, the newest GLIBC_ symbol it references.
PLATFORMS = {
    "aarch64-apple-darwin": "macosx_11_0_arm64",
    "x86_64-apple-darwin": "macosx_10_12_x86_64",
    "x86_64-unknown-linux-gnu": "manylinux_2_39_x86_64",
}

INIT = '''"""The `streamform` binary, packaged for pip. See https://pypi.org/project/streamform-bin/."""

from pathlib import Path

__version__ = "{version}"


def binary() -> Path:
    """The path of the bundled `streamform` binary."""
    return Path(__file__).parent / "bin" / "streamform"
'''

MAIN = '''import os
import sys

from . import binary


def main() -> None:
    """Run the bundled binary in this process's place, with the same arguments."""
    path = str(binary())
    if sys.platform == "win32":
        import subprocess

        raise SystemExit(subprocess.call([path, *sys.argv[1:]]))
    os.execv(path, [path, *sys.argv[1:]])


if __name__ == "__main__":
    main()
'''

README = """# streamform-bin

The `streamform` binary, packaged for pip: `pip install streamform-bin` puts the
`streamform` command on the environment's PATH. It is the same binary as the
release archives, checked against the release's checksums when the wheel was
built, and it is free to use under the terms of use in this package's licence
file.

`streamform-test`, the testing library for Python, depends on it, so
`pip install streamform-test` brings the binary along.

From Python, `streamform_bin.binary()` is the binary's path.
"""


def _record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"sha256={digest}"


def _checksums(assets: Path) -> dict[str, str]:
    sums = {}
    for line in (assets / "checksums.txt").read_text().splitlines():
        if line.strip():
            digest, name = line.split()
            sums[name.lstrip("*")] = digest
    return sums


def _binary_from(archive: Path, expected: str) -> bytes:
    data = archive.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise SystemExit(f"{archive.name}: checksum {actual} does not match checksums.txt {expected}")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member = tar.getmember("streamform")
        extracted = tar.extractfile(member)
        if extracted is None:
            raise SystemExit(f"{archive.name}: `streamform` is not a file")
        return extracted.read()


def _add(zf: zipfile.ZipFile, record: list[str], path: str, data: bytes, executable: bool = False) -> None:
    info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    zf.writestr(info, data)
    record.append(f"{path},{_record_hash(data)},{len(data)}")


def build(assets: Path, version: str, out: Path, partial: bool = False) -> list[Path]:
    sums = _checksums(assets)
    terms = (assets / "LICENSE").read_bytes()
    out.mkdir(parents=True, exist_ok=True)
    built = []
    for target, tag in PLATFORMS.items():
        archive = f"streamform-{target}.tar.gz"
        if archive not in sums:
            if partial:
                continue
            raise SystemExit(f"{archive} is not in checksums.txt")
        binary = _binary_from(assets / archive, sums[archive])
        info = f"{NAME}-{version}.dist-info"
        wheel = out / f"{NAME}-{version}-py3-none-{tag}.whl"
        record: list[str] = []
        metadata = "\n".join([
            "Metadata-Version: 2.4",
            f"Name: {DIST}",
            f"Version: {version}",
            "Summary: The streamform binary, packaged for pip.",
            "License-File: LICENSE",
            "Requires-Python: >=3.9",
            "Description-Content-Type: text/markdown",
            "",
            README,
        ])
        wheel_file = "\n".join([
            "Wheel-Version: 1.0",
            "Generator: streamform-test bin/build_wheels.py",
            "Root-Is-Purelib: false",
            f"Tag: py3-none-{tag}",
            "",
        ])
        with zipfile.ZipFile(wheel, "w") as zf:
            _add(zf, record, f"{NAME}/__init__.py", INIT.format(version=version).encode())
            _add(zf, record, f"{NAME}/__main__.py", MAIN.encode())
            _add(zf, record, f"{NAME}/bin/streamform", binary, executable=True)
            _add(zf, record, f"{info}/entry_points.txt",
                 b"[console_scripts]\nstreamform = streamform_bin.__main__:main\n")
            _add(zf, record, f"{info}/licenses/LICENSE", terms)
            _add(zf, record, f"{info}/METADATA", metadata.encode())
            _add(zf, record, f"{info}/WHEEL", wheel_file.encode())
            record.append(f"{info}/RECORD,,")
            zf.writestr(f"{info}/RECORD", "\n".join(record) + "\n")
        built.append(wheel)
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    parser.add_argument("--partial", action="store_true", help="skip platforms whose archive is absent (local testing)")
    args = parser.parse_args()
    for wheel in build(args.assets, args.version, args.out, args.partial):
        print(wheel)


if __name__ == "__main__":
    main()
