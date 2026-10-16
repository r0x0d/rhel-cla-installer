#!/usr/bin/env python3
"""Regenerate .konflux/artifacts/artifacts.lock.yaml for the galaxy collections.

Konflux hermetic builds cannot reach galaxy.ansible.com, so the collection
tarballs are prefetched by Hermeto's generic fetcher from the lockfile.
This script delegates dependency resolution to ansible-galaxy: it downloads
the full dependency closure of requirements/requirements.yml — direct and
transitive dependencies alike — into a throwaway directory, then rewrites
the lockfile with the sha256 of each tarball and its galaxy download URL,
derived from the identity the collection declares in its MANIFEST.json.

Run it after changing requirements/requirements.yml:

    python3 scripts/artifacts-lock.py    (or: make artifacts-lock)

Requires ansible-galaxy (ansible-core), ruamel.yaml, and network access
to galaxy.ansible.com.
"""

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile

from functools import partial
from pathlib import Path
from typing import IO

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = REPO_ROOT / "requirements" / "requirements.yml"
LOCKFILE = REPO_ROOT / ".konflux" / "artifacts" / "artifacts.lock.yaml"
GALAXY_SERVER = "https://galaxy.ansible.com"
GALAXY_ARTIFACTS_URL = GALAXY_SERVER + "/api/v3/plugin/ansible/content/published/collections/artifacts"


def sha256sum(path: Path) -> str:
    """Hex sha256 of a file, read in chunks to bound memory use."""

    digest = hashlib.sha256()
    # Align the chunks with the hash function block size.
    block_size = (1024 * 1024) // digest.block_size * digest.block_size
    with path.open("rb") as file:
        for chunk in iter(partial(file.read, block_size), b""):
            digest.update(chunk)

    return digest.hexdigest()


def artifact_entry(tarball: Path) -> dict:
    """Turn a downloaded collection tarball into a lockfile entry."""

    with tarfile.open(tarball) as archive:
        info = json.load(archive.extractfile("MANIFEST.json"))["collection_info"]

    namespace = info["namespace"]
    name = info["name"]
    version = info["version"]
    filename = f"{namespace}-{name}-{version}.tar.gz"
    return {
        "download_url": f"{GALAXY_ARTIFACTS_URL}/{filename}",
        "checksum": f"sha256:{sha256sum(tarball)}",
        "filename": filename,
    }


def download_tarballs(destination: Path) -> list[Path]:
    """Resolve and download the dependency closure with ansible-galaxy."""

    command = [
        "ansible-galaxy",
        "collection",
        "download",
        "--no-cache",
        "--requirements",
        REQUIREMENTS_FILE,
        "--download-path",
        destination,
    ]
    try:
        result = subprocess.run(command)
    except FileNotFoundError:
        sys.exit("ansible-galaxy not found on PATH; install ansible-core")
        
    if result.returncode != 0:
        sys.exit(f"ansible-galaxy exited with {result.returncode}")

    tarballs = sorted(destination.glob("*.tar.gz"))
    if not tarballs:
        sys.exit("ansible-galaxy did not download any collections")

    return tarballs


def generate_lockfile() -> None:
    if not REQUIREMENTS_FILE.is_file():
        sys.exit(f"Missing {REQUIREMENTS_FILE}")

    print(f"Resolving {REQUIREMENTS_FILE.relative_to(REPO_ROOT)} with ansible-galaxy...")
    with tempfile.TemporaryDirectory() as destination:
        # Read and hash inside the context: the tarballs vanish with it.
        entries = [artifact_entry(tarball) for tarball in download_tarballs(Path(destination))]

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)  # sequences indented under their key
    yaml.width = 4096  # keep the long galaxy URLs on one line
    with LOCKFILE.open("w") as file:
        file.write(
            "---\n"
            "# Managed by scripts/artifacts-lock.py -- do not edit by hand.\n"
            "# Regenerate after changing requirements/requirements.yml:\n"
            "#   make artifacts-lock\n"
        )
        yaml.dump({"metadata": {"version": "1.0"}, "artifacts": entries}, file)

    print(f"Wrote {LOCKFILE.relative_to(REPO_ROOT)} ({len(entries)} artifacts)")


def main():
    generate_lockfile()

if __name__ == "__main__":
    main()
