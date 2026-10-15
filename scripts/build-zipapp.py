#!/usr/bin/env python3
import platform
import shutil
import subprocess
import venv

from pathlib import Path


def create_venv(name: str) -> Path:
    target_venv = Path("/opt/venvs") / name
    venv.create(target_venv, clear=True, with_pip=True)

    return target_venv


def install_build_deps() -> None:
    """Install required packages only for s390x"""

    arch = platform.machine()
    packages = [
        "gcc",
        "libffi-devel",
        "openssl-devel",
        "python3-devel",
        "rust-toolset",
    ]
    # fmt: off
    command = [
        "dnf", "install", "-y",
        "--setopt", "install_weak_deps=False",
        "--setopt", "tsflags=nodocs",
        *packages,
    ]
    # fmt: on
    if arch == "s390x":
        print(f"Installing build dependencies for {arch}...")
        subprocess.check_call(command)


def main():
    install_build_deps()

    setup = Path("/opt/setup")

    # Install shiv
    print("Installing build tools...")
    build_venv = create_venv("tools")
    build_venv_python = build_venv / "bin" / "python"
    subprocess.check_call(
        [
            build_venv_python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            setup / "requirements-build-3.12.txt",
        ]
    )

    # Build Ansible venv
    print("Building installer...")
    ansible_venv = create_venv("ansible")
    ansible_venv_python = ansible_venv / "bin" / "python"
    subprocess.check_call(
        [
            ansible_venv_python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            setup / "requirements-3.12.txt",
        ]
    )

    # Install collections if a requirements file exists
    ansible_site_packages = Path(
        subprocess.check_output(
            [ansible_venv_python, "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"], text=True
        ).strip()
    )
    galaxy_requirements = setup / "requirements.yml"
    if galaxy_requirements.is_file():
        print("Installing collections...")
        ansible_galaxy = ansible_venv / "bin" / "ansible-galaxy"
        subprocess.check_call(
            [ansible_galaxy, "collection", "install", "-r", galaxy_requirements, "-p", setup / "ansible_collections"]
        )

    shutil.copytree("/opt/setup/ansible_collections", ansible_site_packages / "ansible_collections")

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
