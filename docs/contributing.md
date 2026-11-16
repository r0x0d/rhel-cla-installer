# Contributing #

## Dependency Management

Konflux builds this image [hermetically](https://konflux-ci.dev/docs/building/hermetic-builds/)
(with no network access in the container build). Every dependency is either
pinned in the repository or prefetched by the
[Hermeto](https://hermetoproject.github.io/hermeto/) `prefetch-dependencies`
task, driven by the `prefetch-input` parameter of
`.tekton/pipeline-build-multiarch.yaml`. Regenerate the files below whenever
the matching inputs change, and commit the results.

### Pip dependencies

```
make pip-deps
```

Runs `pip-compile` (requires `python3.12` and network access) on each
`requirements/*.in` file and writes hash-pinned files to `.konflux/pip/`:

* `requirements.in` -> `requirements-3.12.txt`: installer runtime dependencies.
* `requirements-tools.in` -> `requirements-tools-3.12.txt`: zipapp tooling (`shiv`).
* `requirements-build.in` / `requirements-build-legacy.in` ->
  `requirements-build[-legacy]-3.12.txt`: PEP 517 build backends needed to
  compile sdists from source. They are listed by hand (the comments say which
  package needs each); the legacy file holds older versions that some sdists cap.
  If the build fails with `No matching distribution found for <backend><N>`,
  add that backend or version to the matching `.in` file.

### Artifacts (galaxy collections)

```
make artifacts-lock
```

Pins the Ansible collections from `requirements/requirements.yml` into
`.konflux/artifacts/artifacts.lock.yaml` (requires network access to galaxy.ansible.com).

### RPMs

```
make rpm-lock
```

Resolves `.konflux/rpms/rpms.in.yaml` into `.konflux/rpms/rpms.lock.yaml` with
`rpm-lockfile-prototype` (requires `podman`). Rerun when the base image in the
`Containerfile` or the input file changes. See
[Base image updates](base-image-updates.md) for why this matters and how to
verify it after a digest bump.

### Testing locally

```
make hermeto-prefetch
```

Runs the same Hermeto image and input as the pipeline against the pip, RPM and
artifacts inputs (requires `podman`; output lands in `.hermeto-out/`).
