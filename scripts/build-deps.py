#!/usr/bin/env python3
"""Regenerate the requirements Hermeto prefetches for the Konflux build.

Source of truth is pyproject.toml + uv.lock (the installer itself is never
built as a Python package). This script turns the lock into the flat,
hash-pinned requirements files the hermetic build consumes:

  requirements/requirements-3.12.txt        installer runtime deps (uv export)
  requirements/requirements-tools-3.12.txt  zipapp tooling, i.e. shiv (uv export)
  requirements/requirements-build.txt       PEP 517 build backends of everything
                                            compiled from source
  requirements/requirements-build-pypi.txt  build backends missing from the CI
                                            package registry proxy (PyPI direct)
  requirements/requirements-build-dateutil.txt  legacy setuptools-scm pin for
                                            python-dateutil's build backend

Hashes come from uv.lock (exports) and PyPI (compiles), so both Hermeto at
prefetch time and pip's --require-hashes at install time verify every
artifact.

Run it after changing pyproject.toml or uv.lock:

    python3 scripts/build-deps.py    (or: make build-deps)

Requires uv and network access to pypi.org.
"""

import shutil
import subprocess

from pathlib import Path


UV = shutil.which("uv") or "uv"

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_DIR = REPO_ROOT / "requirements"

# Must match the Python version of the builder image.
PYTHON_VERSION = "3.12"

RUNTIME_FILE = REQUIREMENTS_DIR / f"requirements-{PYTHON_VERSION}.txt"
TOOLS_FILE = REQUIREMENTS_DIR / f"requirements-tools-{PYTHON_VERSION}.txt"
BUILD_FILE = REQUIREMENTS_DIR / "requirements-build.txt"
BUILD_PYPI_FILE = REQUIREMENTS_DIR / "requirements-build-pypi.txt"
BUILD_DATEUTIL_FILE = REQUIREMENTS_DIR / "requirements-build-dateutil.txt"

# Hermeto scopes --index-url per requirements file; this one must bypass the
# Konflux package registry proxy (see requirements-build-pypi.in).
PYPI_INDEX_URL = "--index-url https://pypi.org/simple/"


def uv(*args: str) -> None:
    subprocess.run([UV, *args], check=True)


def export(output: Path, *extra: str) -> None:
    """Freeze a requirements file from uv.lock."""
    uv(
        "export", "--frozen", "--no-emit-project", "--no-header", "--no-annotate",
        "--python", PYTHON_VERSION, *extra, "--output-file", str(output),
    )


def compile(output: Path, inputs: list[Path], *, no_deps: bool = False, excludes: Path | None = None) -> None:
    """Pin (and hash) a requirements file from its .in inputs."""
    args = [
        "pip", "compile", "--generate-hashes", "--no-header", "--no-annotate",
        "--python-version", PYTHON_VERSION, "--output-file", str(output),
    ]
    if no_deps:
        args.append("--no-deps")
    if excludes is not None:
        args += ["--excludes", str(excludes)]
    uv(*args, *[str(i) for i in inputs])


def count_packages(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line and line[0].isalpha())


def main() -> None:
    print("Exporting requirements from uv.lock...")
    # --no-dev keeps local tooling (e.g. rpm-lockfile-prototype) out of the
    # installer's runtime requirements.
    export(RUNTIME_FILE, "--no-dev")
    export(TOOLS_FILE, "--only-group", "tools")

    print("Compiling PEP 517 build requirements...")
    compile(
        BUILD_FILE,
        [REQUIREMENTS_DIR / "requirements-build.in"],
        excludes=REQUIREMENTS_DIR / "requirements-build-pypi.in",
    )
    compile(BUILD_PYPI_FILE, [REQUIREMENTS_DIR / "requirements-build-pypi.in"], no_deps=True)
    compile(BUILD_DATEUTIL_FILE, [REQUIREMENTS_DIR / "requirements-build-dateutil.in"], no_deps=True)

    # Point the proxy-bypassing file straight at PyPI.
    content = BUILD_PYPI_FILE.read_text()
    BUILD_PYPI_FILE.write_text(f"{PYPI_INDEX_URL}\n\n{content}")

    for path in (RUNTIME_FILE, TOOLS_FILE, BUILD_FILE, BUILD_PYPI_FILE, BUILD_DATEUTIL_FILE):
        print(f"Wrote {path.relative_to(REPO_ROOT)} ({count_packages(path)} packages)")
    print("Remember to commit the regenerated files.")


if __name__ == "__main__":
    main()
