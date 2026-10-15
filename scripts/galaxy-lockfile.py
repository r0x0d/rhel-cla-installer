#!/usr/bin/env python3
"""Regenerate requirements/artifacts.lock.yaml for the galaxy collections.

Konflux hermetic builds cannot reach galaxy.ansible.com, so the collection
tarballs are prefetched by Hermeto's generic fetcher from
requirements/artifacts.lock.yaml. This script resolves the full dependency
closure of requirements/requirements.yml — direct and transitive
dependencies alike — against the galaxy API, then rewrites the lockfile
with the download URL and sha256 checksum galaxy records for each resolved
version. Nothing is downloaded here: if an artifact ever drifts from its
recorded checksum, Hermeto fails the Konflux prefetch step.

Transitive dependencies resolve to the newest released version satisfying
the dependency spec, pre-releases excluded, matching what ansible-galaxy
installs for a local build.

Run it after changing requirements/requirements.yml:

    python3 scripts/galaxy-lockfile.py    (or: make galaxy-lockfile)

Requires PyYAML and network access to galaxy.ansible.com.
"""

import json
import urllib.error
import urllib.request

from collections import deque
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = REPO_ROOT / "requirements" / "requirements.yml"
LOCKFILE = REPO_ROOT / "requirements" / "artifacts.lock.yaml"

GALAXY_SERVER = "https://galaxy.ansible.com"
GALAXY_VERSION_URL = (
    GALAXY_SERVER + "/api/v3/plugin/ansible/content/published/"
    "collections/index/{namespace}/{name}/versions/{version}/"
)
GALAXY_VERSIONS_URL = (
    GALAXY_SERVER + "/api/v3/plugin/ansible/content/published/"
    "collections/index/{namespace}/{name}/versions/"
)
MAX_PAGES = 100


# Indent list items under their key, matching the existing lockfile style.
class IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def galaxy_request(url: str) -> dict:
    """GET a galaxy API endpoint and return its JSON response."""

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except urllib.error.URLError as error:
        raise SystemExit(f"Galaxy API request to {url} failed: {error}")


def galaxy_version_detail(namespace: str, name: str, version: str) -> dict:
    """Fetch the detail of one collection version.

    Includes the artifact block (filename, sha256, size), the canonical
    download URL, and the manifest with the dependency map.
    """

    return galaxy_request(
        GALAXY_VERSION_URL.format(namespace=namespace, name=name, version=version)
    )


def galaxy_collection_versions(namespace: str, name: str) -> list[str]:
    """List every published version of a collection."""

    url = GALAXY_VERSIONS_URL.format(namespace=namespace, name=name) + "?limit=100"
    versions = []

    for _ in range(MAX_PAGES):
        page = galaxy_request(url)
        versions += [entry["version"] for entry in page["data"]]
        next_page = page["links"]["next"]
        if next_page is None:
            if not versions:
                # The versions endpoint answers 200 with an empty list for
                # unknown collections, so surface the real problem here.
                raise SystemExit(
                    f"Collection {namespace}.{name} not found on galaxy "
                    "(or it has no published versions)."
                )
            return versions
        url = GALAXY_SERVER + next_page

    raise SystemExit(f"Galaxy version list for {namespace}.{name} exceeds {MAX_PAGES} pages")


def version_sort_key(version: str) -> tuple:
    """Sort key for semver-ish versions; releases sort after pre-releases.

    Pre-release identifiers are compared as plain strings, which is fine
    here because pre-releases are never selected from range specs anyway.
    """

    version = version.split("+", 1)[0]  # drop build metadata
    core, _, prerelease = version.partition("-")
    return (tuple(int(part) for part in core.split(".")), not prerelease, prerelease)


def parse_constraints(spec: str) -> list[tuple[str, str]]:
    """Parse a galaxy version spec into (operator, version) constraints.

    Supports exact versions, "*", and comma-separated combinations of
    "==", "!=", ">=", "<=", ">", "<".
    """

    if spec == "*":
        return []

    constraints = []
    for part in spec.split(","):
        part = part.strip()
        for operator in ("==", "!=", ">=", "<=", ">", "<"):
            if part.startswith(operator):
                constraints.append((operator, part[len(operator):]))
                break
        else:
            if any(character in part for character in "=<>!"):
                raise SystemExit(f"Unsupported version spec: {spec!r}")
            constraints.append(("==", part))
    return constraints


def satisfies(version: str, constraints: list[tuple[str, str]]) -> bool:
    """Check a version against parsed constraints."""

    key = version_sort_key(version)
    for operator, target in constraints:
        target_key = version_sort_key(target)
        if operator == "==" and key != target_key:
            return False
        if operator == "!=" and key == target_key:
            return False
        if operator == ">=" and key < target_key:
            return False
        if operator == "<=" and key > target_key:
            return False
        if operator == ">" and key <= target_key:
            return False
        if operator == "<" and key >= target_key:
            return False
    return True


def pick_version(namespace: str, name: str, spec: str) -> str:
    """Resolve a version spec to a concrete version.

    Exact specs resolve directly; range specs pick the newest satisfying
    release, pre-releases excluded (like ansible-galaxy).
    """

    constraints = parse_constraints(spec)
    exact = [target for operator, target in constraints if operator == "=="]

    if exact and len(exact) == len(constraints):
        return exact[0]

    versions = galaxy_collection_versions(namespace, name)
    candidates = [
        version for version in versions
        if satisfies(version, constraints) and "-" not in version
    ]
    if not candidates:
        raise SystemExit(
            f"No released version of {namespace}.{name} satisfies {spec!r} "
            f"(available: {', '.join(versions)})"
        )
    return max(candidates, key=version_sort_key)


def parse_requirements() -> list[tuple[str, str, str]]:
    """Read requirements.yml into (namespace, name, version spec) triples."""

    requirements = yaml.safe_load(REQUIREMENTS_FILE.read_text())
    if not isinstance(requirements, dict) or not requirements.get("collections"):
        raise SystemExit(f"No collections listed in {REQUIREMENTS_FILE}")

    triples = []
    for entry in requirements["collections"]:
        if not isinstance(entry, dict):
            raise SystemExit(f"Invalid collection entry {entry!r} in {REQUIREMENTS_FILE}")
        namespace, separator, name = entry.get("name", "").partition(".")
        if not separator or not namespace or not name:
            raise SystemExit(f"Invalid collection name {entry.get('name')!r} in {REQUIREMENTS_FILE}")
        triples.append((namespace, name, str(entry.get("version", "*"))))
    return triples


def resolve_closure(direct: list[tuple[str, str, str]]) -> dict[tuple[str, str], dict]:
    """Resolve the dependency closure of the direct requirements.

    Returns (namespace, name) -> galaxy version detail for every collection
    in the closure. Conflicting requirements fail loudly rather than
    silently picking one side.
    """

    details: dict[tuple[str, str], dict] = {}
    resolved_specs: dict[tuple[str, str], str] = {}
    pending = deque(direct)

    while pending:
        namespace, name, spec = pending.popleft()
        key = (namespace, name)

        if key in resolved_specs:
            if resolved_specs[key] == spec:
                continue  # requirement already processed
            if not satisfies(details[key]["version"], parse_constraints(spec)):
                raise SystemExit(
                    f"Conflicting requirements for {namespace}.{name}: "
                    f"{resolved_specs[key]!r} resolved to {details[key]['version']}, "
                    f"which does not satisfy {spec!r}"
                )
            continue

        version = pick_version(namespace, name, spec)
        detail = galaxy_version_detail(namespace, name, version)
        details[key] = detail
        resolved_specs[key] = spec
        print(f"Resolved {namespace}.{name} {version}")

        dependencies = detail["manifest"]["collection_info"].get("dependencies") or {}
        for fqcn, dependency_spec in dependencies.items():
            dependency_namespace, separator, dependency_name = fqcn.partition(".")
            if not separator:
                raise SystemExit(f"Invalid dependency {fqcn!r} of {namespace}.{name}")
            pending.append((dependency_namespace, dependency_name, dependency_spec))

    return details


def lock_entries(details: dict[tuple[str, str], dict]) -> list[dict]:
    """Turn resolved version details into lockfile entries."""

    entries = []
    for (_namespace, _name), detail in details.items():
        artifact = detail["artifact"]
        entries.append({
            "download_url": detail["download_url"],
            "checksum": f"sha256:{artifact['sha256']}",
            "filename": artifact["filename"],
        })

    return sorted(entries, key=lambda entry: entry["filename"])


def main():
    if not REQUIREMENTS_FILE.is_file():
        raise SystemExit(f"Missing {REQUIREMENTS_FILE}")

    print(f"Resolving {REQUIREMENTS_FILE.relative_to(REPO_ROOT)}...")
    entries = lock_entries(resolve_closure(parse_requirements()))

    contents = yaml.dump(
        {"metadata": {"version": "1.0"}, "artifacts": entries},
        Dumper=IndentedDumper,
        default_flow_style=False,
        sort_keys=False,
        width=4096,
    )
    LOCKFILE.write_text(
        "---\n"
        "# Managed by scripts/galaxy-lockfile.py -- do not edit by hand.\n"
        "# Regenerate after changing requirements/requirements.yml:\n"
        "#   make galaxy-lockfile\n"
        + contents
    )
    print(f"Wrote {LOCKFILE.relative_to(REPO_ROOT)} ({len(entries)} artifacts)")


if __name__ == "__main__":
    main()
