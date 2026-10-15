#!/bin/bash
# scripts/install-toolchain.sh — Install the C/Rust toolchain for from-source builds.
#
# The hermetic Konflux build compiles every Python wheel from source
# (BUILD_FROM_SOURCE=1, a Product Security requirement), and the builder
# image ships no compiler or Python headers. This script installs the
# toolchain listed in requirements/rpms.in.yaml.
#
# In hermetic builds the RPMs are prefetched by Hermeto
# (requirements/rpms.lock.yaml) and
# konflux-build-cli injects a file:// repo into /etc/yum.repos.d; the image's
# own network repos are unreachable under --network none, so the build is
# restricted to the injected hummingbird repo (a second repo with the runtime
# image's RPMs is injected too, see requirements/rpms.in.yaml).
#
# Local builds cannot use the image's baked-in repo (its packages.redhat.com
# URL is unreliable), so a repo pointing at the public Hummingbird pulp
# content on console.redhat.com is written instead.
set -euo pipefail

# Exit early for prebuilt-wheel builds that need no toolchain.
if [[ "${BUILD_FROM_SOURCE:-1}" != "1" ]]; then
    echo "install-toolchain.sh: BUILD_FROM_SOURCE=${BUILD_FROM_SOURCE:-1}, skipping toolchain install"
    exit 0
fi

# --allowerasing: the base image ships glibc-minimal-langpack which conflicts
# with glibc-devel's glibc dependency when a newer glibc is in the repo.
dnf_args=(--allowerasing)

hermeto_repo=$(grep -lm1 hummingbird /etc/yum.repos.d/*.repo 2>/dev/null | head -1 || true)
if [[ -f /cachi2/cachi2.env && -n "$hermeto_repo" ]]; then
    echo "install-toolchain.sh: using Hermeto-prefetched RPMs from $hermeto_repo"
    # The injected hermeto.repo carries every repoid of the build (this
    # toolchain plus the runtime image's RPMs) - pick the hummingbird one.
    repo_id=$(sed -n 's/^\[\([^]]*hummingbird[^]]*\)\].*/\1/p' "$hermeto_repo" | head -1)
    dnf_args+=(--disablerepo='*' --enablerepo="$repo_id")
else
    echo "install-toolchain.sh: local build, using the public Hummingbird repo"
    cat >/etc/yum.repos.d/local-hummingbird.repo <<'EOF'
[local-hummingbird-rpms]
name=Public Hummingbird RPMs
baseurl=https://console.redhat.com/api/pulp-content/public-hummingbird/$basearch/
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-hummingbird-release
gpgcheck=1
enabled=1
EOF
    dnf_args+=(--disablerepo='*' --enablerepo=local-hummingbird-rpms)
fi

# NOTE: keep this list in sync with requirements/rpms.in.yaml and regenerate
# requirements/rpms.lock.yaml
# after any change (make rpm-lock). Python 3.12 and pip are already in the
# builder image.
dnf install -y "${dnf_args[@]}" \
    python3.12-devel \
    gcc \
    gcc-c++ \
    openssl-devel \
    rust \
    cargo \
    pkgconf \
    libffi-devel

dnf clean all
