#!/usr/bin/env python3
import os
import shutil
import subprocess
import venv

from pathlib import Path


# Compile wheels from source (Product Security requirement) unless overridden
# for fast local builds; hermetic Konflux builds prefetch source distributions
# only, so from-source is the only mode that works there.
BUILD_FROM_SOURCE = os.environ.get("BUILD_FROM_SOURCE", "1") == "1"


def create_venv(name: str) -> Path:
    target_venv = Path("/opt/venvs") / name
    venv.create(target_venv, clear=True, with_pip=True)

    return target_venv


def install_requirements(venv_python: Path, requirements: str) -> None:
    """Install a hash-pinned requirements file into a virtual environment.

    Under hermetic builds pip resolves from the prefetched store
    (PIP_FIND_LINKS/PIP_NO_INDEX are set in the environment), otherwise from
    PyPI. The PEP 517 build backends needed to compile the source
    distributions are prefetched as well (requirements/requirements-build*.txt)
    and installed by pip into each package's isolated build environment.
    """
    binary_flags = ["--no-binary=:all:"] if BUILD_FROM_SOURCE else ["--only-binary=:all:"]
    subprocess.check_call(
        [
            venv_python, "-m", "pip", "install",
            "--no-cache-dir", "--require-hashes", *binary_flags,
            "-r", requirements,
        ]
    )


def install_collections(ansible_galaxy: Path) -> None:
    """Install the galaxy collections into the staging layout.

    Both modes install with ansible-galaxy for an identical layout. Konflux
    hermetic builds have no network access and install the prefetched
    tarballs with --offline (their full dependency closure is pinned in
    requirements/artifacts.lock.yaml by scripts/galaxy-lockfile.py). Local
    builds install the pinned collections from galaxy.ansible.com.
    """
    # We store out collections in a non-standard location that ansible-galaxy does not recognize.
    collections_path = Path("/opt/setup/collections")

    # The default command used in both offline/online. The specifics for each scenario is appended below.
    command = [str(ansible_galaxy), "collection", "install", "-p", str(collections_path)]

    # Konflux hermetic builds serve the tarballs prefetched by Hermeto's
    # generic fetcher (requirements/artifacts.lock.yaml) from
    # /cachi2/output/deps/generic. The directory only exists in those builds;
    # local builds get an empty list back and fetch the collections from
    # galaxy.ansible.com instead.
    cachi2_tarballs = sorted(Path("/cachi2/output/deps/generic").glob("*.tar.gz"))

    if cachi2_tarballs:
        print("Installing prefetched collections...")
        command.append("--offline")
        command.extend([str(tarball) for tarball in cachi2_tarballs])
    else:
        print("Installing collections from galaxy.ansible.com...")
        command.extend(["-r", "/opt/setup/requirements.yml"])

    # Point the collections path config at the install target so galaxy
    # does not warn about -p not being a configured collections path.
    env = {**os.environ, "ANSIBLE_COLLECTIONS_PATH": str(collections_path)}
    subprocess.check_call(command, env=env)


def main():
    if BUILD_FROM_SOURCE:
        # Speed up the C/Rust/Cython compilations.
        cpus = str(os.cpu_count() or 1)
        for var in ("CARGO_BUILD_JOBS", "CMAKE_BUILD_PARALLEL_LEVEL", "MAX_JOBS"):
            os.environ.setdefault(var, cpus)
        os.environ.setdefault("MAKEFLAGS", f"-j{cpus}")

    # Install shiv
    print("Installing build tools...")
    build_venv = create_venv("tools")
    build_venv_python = build_venv / "bin" / "python"
    install_requirements(build_venv_python, "/opt/setup/requirements-tools-3.12.txt")

    # Build Ansible venv (also provides ansible-galaxy for local builds)
    print("Building installer...")
    ansible_venv = create_venv("ansible")
    ansible_site_packages = ansible_venv / "lib" / "python3.12" / "site-packages"
    ansible_venv_python = ansible_venv / "bin" / "python"
    install_requirements(ansible_venv_python, "/opt/setup/requirements-3.12.txt")

    # Install galaxy collections and bundle them into the installer venv
    install_collections(ansible_venv / "bin" / "ansible-galaxy")
    shutil.copytree("/opt/setup/collections/ansible_collections", ansible_site_packages / "ansible_collections")

    # Build zipapp
    print("Packaging installer...")
    shiv = build_venv / "bin" / "shiv"
    # fmt: off
    subprocess.check_call([
        shiv, "--site-packages",
        ansible_site_packages,
        "--console-script", "ansible-playbook",
        "--output-file", "/opt/rhel-cla-installer",
    ])
    # fmt: on

    print("Done!")


if __name__ == "__main__":
    main()
