#!/usr/bin/env python3
"""Regenerate the pip requirements Hermeto prefetches for the Konflux build.

Source of truth is requirements/requirements.in (the installer itself is
never built as a Python package). This script compiles it into the flat,
hash-pinned requirements files the hermetic build consumes:

  .konflux/pip/requirements-3.12.txt        installer runtime dependencies
  .konflux/pip/requirements-build-3.12.txt  zipapp build tooling (shiv)

Requirements for packages listed in BUILD_TOOLS are kept out of the
installer and compiled into the build file instead.

Hashes let both Hermeto at prefetch time and pip's --require-hashes at
install time verify every artifact.

Run it after changing requirements/requirements.in:

    python3 scripts/build-deps.py    (or: make build-deps)

Requires python3.12 on PATH (the builder image version) and network access
to pypi.org; pip-compile is bootstrapped with pip into a throwaway virtual
environment so dependency resolution matches the builder.
"""

import re
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path


# Must match the Python version of the builder image: pip-compile evaluates
# environment markers against the interpreter it runs under.
PYTHON_VERSION = "3.12"

# Tooling used to build the zipapp; kept out of the installer itself.
BUILD_TOOLS = ("shiv",)

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_IN = REPO_ROOT / "requirements" / "requirements.in"
CONSTRAINTS = REPO_ROOT / "requirements" / "constraints.txt"
OUTPUT_DIR = REPO_ROOT / ".konflux" / "pip"


def package_name(requirement: str) -> str:
    """Name part of a requirement line, e.g. 'ansible-core<2.19' -> 'ansible-core'."""
    return re.split(r"[\s<>=!~;\[]", requirement, maxsplit=1)[0].lower()


def read_requirements() -> list[str]:
    """Non-empty, non-comment requirement lines."""
    lines = REQUIREMENTS_IN.read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def bootstrap_pip_compile(venv_dir: Path) -> Path:
    """Install pip-compile into a throwaway venv of the builder's Python version."""
    python = shutil.which(f"python{PYTHON_VERSION}")
    if python is None:
        sys.exit(f"error: python{PYTHON_VERSION} not found on PATH (must match the builder image)")
    subprocess.run([python, "-m", "venv", str(venv_dir)], check=True)
    pip = venv_dir / "bin" / "pip"
    subprocess.run([pip, "install", "--quiet", "--disable-pip-version-check", "pip-tools"], check=True)
    return venv_dir / "bin" / "pip-compile"


def compile_requirements(pip_compile: Path, output: Path, requirements: list[str]) -> None:
    """Resolve and hash-pin the given requirements into output."""
    with tempfile.TemporaryDirectory() as tmp:
        # pip-compile takes requirement files, not arguments, so hand it a
        # temporary .in holding just the requirements to resolve.
        src = Path(tmp) / "requirements.in"
        src.write_text("\n".join(requirements) + "\n")
        subprocess.run(
            [
                pip_compile,
                "--quiet",
                "--generate-hashes",
                # pip/setuptools (shiv dependencies) are hidden without this.
                "--allow-unsafe",
                # Header and annotations would embed the temporary .in path.
                "--no-header",
                "--no-annotate",
                # Keep extras (e.g. "pkg[extra]") explicit; none are used today.
                "--no-strip-extras",
                # Resolve fresh instead of reusing the pins of an existing output file.
                "--upgrade",
                "--constraint",
                str(CONSTRAINTS),
                "--output-file",
                str(output),
                str(src),
            ],
            check=True,
        )


def count_packages(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line and line[0].isalpha())


def main() -> None:
    requirements = read_requirements()
    build = [r for r in requirements if package_name(r) in BUILD_TOOLS]
    runtime = [r for r in requirements if package_name(r) not in BUILD_TOOLS]
    if not build:
        sys.exit(f"error: no build tools ({', '.join(BUILD_TOOLS)}) in {REQUIREMENTS_IN}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Bootstrapping pip-compile with Python {PYTHON_VERSION}...")
        pip_compile = bootstrap_pip_compile(Path(tmp) / "venv")
        print("Compiling installer runtime requirements...")
        compile_requirements(pip_compile, OUTPUT_DIR / f"requirements-{PYTHON_VERSION}.txt", runtime)
        print("Compiling zipapp build tooling...")
        compile_requirements(pip_compile, OUTPUT_DIR / f"requirements-build-{PYTHON_VERSION}.txt", build)

    for path in sorted(OUTPUT_DIR.glob("*.txt")):
        print(f"Wrote {path.relative_to(REPO_ROOT)} ({count_packages(path)} packages)")
    print("Remember to commit the regenerated files.")


if __name__ == "__main__":
    main()
