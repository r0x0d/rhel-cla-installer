# Red Hat Enterprise Linux Command Line Assistant Installer #

This is the installer for the self-managed RHEL CLA. It supports local, remote installations. OpenShift support is stil in development.

## Prerequisites ##

- Python 3.11 or later
- [`podman`]
- A [Red Hat Offline Knowledge Portal key][rhokp_key]
- 30GB of free disk space for the Red Hat Offline Knowledge Portal.
- Valid login credentials in `/etc/containers/auth.json`.

Create the required login credentials. This needs to be done on both local and remote systems, or the auth file can be generated once and copied to remote systems.

```
sudo podman login --authfile /etc/containers/auth.json registry.redhat.io
```

## Local Installation ##

1. Extract the installer from the container image in order to run it against `localhost`.

    ```
    ./scripts/extract.sh
    ```

    This will extract the installer from the container into a single executable to a `local` directory.

    If any errors are encountered when extracting the installer, run `bash -s scripts/extract.sh` to see more verbose output.

    It is possible to override `IMAGE` and `CONTAINER_RUNTIME` if needed.

    ```
    CONTAINER_RUNTIME=docker ./scripts/extract.sh
    ```

1. Configure inventory.

    Make a copy of the example inventory file and fill in the required variables.

    ```
    mkdir local/inventory
    cp inventory/hosts.example.yml local/inventory/hosts.yml
    ```

    For local installation, no host definitions are necessary.

1. Run the installer.

    ```
    cd local
    ./rhel-cla-installer rhel.cla.local
    ```

    Adjust verbosity by adding `-v`. More v's give more verbosity.

### Verify Installation ###

Check the pod and container status.

```
sudo systemctl status rhel-cla-pod.service
sudo systemctl status rhel-knowledge-bridge.service
sudo systemctl rh-offline-knowledge-portal.service
sudo systemctl lightspeed-stack.service
```

### Uninstall ###

Run `./rhel-cla-installer rhel.cla.uninstall_local`.

## Dependency Management ##

Konflux builds this image [hermetically](https://konflux-ci.dev/docs/building/hermetic-builds/)
(with no network access in the container build). Every dependency is either
pinned in the repository or prefetched by the
[Hermeto](https://hermetoproject.github.io/hermeto/) `prefetch-dependencies`
task, driven by the `prefetch-input` parameter of
`.tekton/pipeline-build-multiarch.yaml`:

* **Python packages** are declared in `pyproject.toml` (the installer's
  runtime dependencies, plus a `tools` group with `shiv`) and locked in
  `uv.lock`. `scripts/build-deps.py` turns the lock into the flat,
  hash-pinned requirements files Hermeto prefetches: the runtime and tools
  requirements, and `requirements-build*.txt`, the PEP 517 build backends
  (`maturin` for `pydantic-core` and `cryptography`, `setuptools-scm`,
  `flit-core`, ...) needed to compile every sdist. The build installs them
  with `PIP_NO_INDEX` / `PIP_FIND_LINKS` and `--require-hashes`.

  Every wheel is compiled from source inside the build
  (`BUILD_FROM_SOURCE=1`, a Product Security requirement for Konflux) —
  Rust-based packages such as `pydantic` and `cryptography` included. The
  C/Rust toolchain RPMs for that are prefetched by Hermeto as well (see the
  builder toolchain bullet below). Use `--build-arg BUILD_FROM_SOURCE=0`
  for fast local builds from prebuilt manylinux wheels.

  After changing `pyproject.toml`, regenerate the lock and the requirements
  files (requires [uv](https://docs.astral.sh/uv/) and network access to
  pypi.org):

  ```
  make freeze
  ```

  The `requirements-build.in` files carry the version bounds that satisfy
  every package's build backend constraints — when adding or upgrading a
  dependency, check its sdist's `pyproject.toml` `[build-system]` and adjust
  them if needed.
* **Ansible Galaxy collections** are listed (URL + sha256) in
  `requirements/artifacts.lock.yaml` and fetched by Hermeto's *generic
  fetcher* (Galaxy has no dedicated Hermeto support). The lockfile pins the
  full dependency closure of `requirements/requirements.yml`, transitive
  dependencies included, and is managed by `scripts/galaxy-lockfile.py`;
  regenerate it after changing the requirements (requires network access
  to galaxy.ansible.com):

  ```
  make galaxy-lockfile
  ```

  The script only queries the galaxy API — nothing is downloaded — and if
  an artifact ever drifts from its recorded checksum, Hermeto fails the
  Konflux prefetch step. The build installs the collections with
  `ansible-galaxy` either way — hermetic builds from the prefetched
  tarballs (`--offline`), local builds straight from galaxy.ansible.com —
  so a plain `podman build .` needs no extra step.

* **RPMs** for both container stages are resolved in a single lockfile,
  `requirements/rpms.lock.yaml`: the final `ubi10-minimal` stage's `tar`
  from the UBI 10 BaseOS repositories, and the builder stage's C/Rust
  toolchain (`gcc`, `rust`, `cargo`, `python3.12-devel`, ...) from the
  public Hummingbird repository (the builder image's own repo URL is
  unreliable; `scripts/install-toolchain.sh` uses `console.redhat.com`
  directly for local builds). The package list must match
  `scripts/install-toolchain.sh` and the `microdnf install` command in the
  final stage. Regenerate after changing either (uses the containerized
  [rpm-lockfile-prototype](https://github.com/konflux-ci/rpm-lockfile-prototype);
  requires `podman` and network access):

  ```
  make rpm-lock
  ```

The prefetch can be validated locally with the same Hermeto image and input
the pipeline uses (requires `podman`; output lands in `.hermeto-out/`):

```
make hermeto-prefetch
```

The Python version baked into the requirements files (from
`scripts/build-deps.py`), the toolchain package list
(`requirements/rpms.in.yaml` / `scripts/install-toolchain.sh`) and the
`arches` of the RPM lockfile must be kept in sync with the builder image
(`hi/python:3.12-builder`) and the `build-platforms` parameter of
`.tekton/pipeline-build-multiarch.yaml` (`linux/amd64` and `linux/arm64`
by default).


[`podman`]: https://podman.io/
[rhokp_key]: https://access.redhat.com/offline/access/
