# Base image updates #

Both base images in the `Containerfile` are pinned by digest:

* the **builder** image (`registry.access.redhat.com/hi/python:3.12-builder`),
  where the C/Rust toolchain is installed and every wheel is compiled;
* the **runtime** image (`registry.access.redhat.com/ubi10-minimal`), which
  ships the final installer.

The Renovate "Update container base images" PR updates the digests in the
`Containerfile` — but that alone is **not enough to build**. This page explains
what else must be regenerated and how to verify the update.

## Why the RPM lockfile must follow the base image

`.konflux/rpms/rpms.lock.yaml` is resolved by `rpm-lockfile-prototype` with the
**builder image as its context** (see `context:` in `.konflux/rpms/rpms.in.yaml`):
packages already installed in that image are *excluded from the lockfile*,
because the build-time `dnf` will find them already installed.

When the builder image digest changes, its installed package set changes. If
the lockfile is not regenerated, the two drift apart. The classic symptom is a
hermetic build failing during `RUN /opt/setup/install-toolchain.sh` with dnf
errors like:

```
Problem 1: package gcc-16.2.1-3.2.hum1.x86_64 from public-hummingbird-x86_64-rpms
  requires glibc-devel >= 2.2.90-12, but none of the providers can be installed
  - nothing provides glibc = 2.43-9.2.hum1 needed by
    glibc-devel-2.43-9.2.hum1.x86_64 from public-hummingbird-x86_64-rpms
```

What happened here: the *old* builder image had `glibc-2.43-9.2.hum1`
installed, so the lockfile pinned `glibc-devel-2.43-9.2.hum1` and omitted the
binary `glibc` RPM entirely. The *new* builder image ships
`glibc-2.43-9.3.hum1`, so nothing in the container or in the Hermeto-injected
repo can provide `glibc = 2.43-9.2.hum1` anymore — and `gcc`, `gcc-c++`,
`rust` and `cargo` all fail because they depend on `glibc-devel` transitively.

## Procedure

1. Merge or check out the base image update (the `Containerfile` digest bumps).
   The Renovate PR also updates the `context:` image in
   `.konflux/rpms/rpms.in.yaml` to match the new builder digest — verify that
   it did, and update it by hand if not. If they disagree, regenerate the
   lockfile with the wrong image and the build will break exactly as above.

1. Regenerate the RPM lockfile against the new image:

    ```
    make rpm-lock
    ```

    Requires `podman` and network access. Expect version bumps for the
    toolchain packages resolved from the Hummingbird repos (e.g. `gcc`,
    `rust`, `cargo`, `glibc-devel`) and possibly packages *dropped* from the
    lockfile when the new image provides them itself.

1. Review the lockfile diff:

    ```
    git diff .konflux/rpms/rpms.lock.yaml
    ```

    Sanity checks:

    * No package that the toolchain install needs disappeared without the
      image providing it (compare with `podman run --rm <builder-image> rpm -q <pkg>`).
    * Versions that must match an installed package exactly (`glibc` for
      `glibc-devel`, `python3.12` for `python3.12-devel`) line up.

1. Verify the hermetic toolchain install resolves before pushing (see below),
   then commit the lockfile together with the digest bumps.

## Verifying the toolchain install locally

The quickest faithful reproduction of the hermetic `dnf` transaction:

1. Download the RPMs the lockfile pins for your arch and turn them into a
   local repo:

    ```
    mkdir -p /tmp/lockrepo && cd /tmp/lockrepo
    python3 - <<'EOF'
    import yaml
    d = yaml.safe_load(open('.konflux/rpms/rpms.lock.yaml'))
    urls = [p['url'] for a in d['arches'] if a['arch'] == 'x86_64'
            for p in a['packages'] if 'hummingbird/x86_64' in p['url']]
    open('urls.txt', 'w').write('\n'.join(urls))
    EOF
    xargs -P8 -n1 curl -sSfLO < urls.txt
    createrepo_c .
    ```

1. Run the same `dnf install` as `scripts/install-toolchain.sh`, restricted to
   that repo only, inside the new builder image (note `--user 0`: the image's
   default user is unprivileged, the `Containerfile` does `USER 0` for this
   step):

    ```
    podman run --rm --user 0 -v /tmp/lockrepo:/cachi2/repo:ro,z \
      registry.access.redhat.com/hi/python:3.12-builder@<new digest> bash -c '
    cat >/etc/yum.repos.d/hermeto.repo <<EOF
    [public-hummingbird-x86_64-rpms]
    name=Hermeto prefetched RPMs
    baseurl=file:///cachi2/repo
    enabled=1
    gpgcheck=0
    EOF
    dnf install -y --allowerasing --disablerepo="*" \
      --enablerepo=public-hummingbird-x86_64-rpms \
      python3.12-devel gcc gcc-c++ openssl-devel rust cargo pkgconf libffi-devel'
    ```

    A `Complete!` with no solver problems means the lockfile and the new
    builder image agree.

For a full end-to-end check (pip sdists included), use `make hermeto-prefetch`
instead — it runs the same Hermeto image and inputs as the pipeline.

## Runtime image bumps

The runtime image (`ubi10-minimal`) is not used as the lockfile context, so it
does not affect toolchain resolution. Its only locked dependency is `tar`,
installed with `microdnf` in the final stage. A runtime digest bump alone
therefore does not require a lockfile regeneration — but regenerating is
harmless, and running `make rpm-lock` after *any* base image bump is the
simple rule to follow.

## Checklist

- [ ] `Containerfile` digests updated (Renovate PR)
- [ ] `context:` image in `.konflux/rpms/rpms.in.yaml` matches the new builder digest
- [ ] `make rpm-lock` rerun and the lockfile diff reviewed
- [ ] Hermetic toolchain install verified (local repro above, or `make hermeto-prefetch`)
- [ ] Lockfile committed together with the digest bumps
