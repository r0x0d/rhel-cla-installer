# ──────────────────────────────────────────────────────────────────────────────
# builder: Hummingbird Python 3.12 builder image.
#
# Has bash, dnf/dnf5, and pip — everything needed, including `dnf install` on
# s390x for gcc/libffi-devel/openssl-devel/python3-devel/rust-toolset.
# This stage is ephemeral; only /opt/rhel-cla-installer is copied out.
# ──────────────────────────────────────────────────────────────────────────────
FROM registry.access.redhat.com/hi/python:3.12-builder@sha256:83a8d45c8cf97d0581ac4248a2ac2727eb3549165429cc9e072f437a67f33bda AS builder

USER 0

COPY .konflux/pip/*.txt /opt/setup/

# Add the required collections.
COPY collections/ansible_collections/ /opt/setup/collections/ansible_collections/

COPY scripts/build-zipapp.py scripts/install-toolchain.sh /opt/setup/

# Build from source by default (Product Security requirement for Konflux):
# every wheel is compiled inside the build instead of using prebuilt
# manylinux wheels. Override with --build-arg BUILD_FROM_SOURCE=0 for fast
# local builds from prebuilt wheels (not available in hermetic builds,
# which prefetch source distributions only).
ARG BUILD_FROM_SOURCE=1
ENV BUILD_FROM_SOURCE=${BUILD_FROM_SOURCE}

# C/Rust toolchain for compiling the wheels (no-op when BUILD_FROM_SOURCE=0).
# Hermetic builds install the RPMs Hermeto prefetched
RUN /opt/setup/install-toolchain.sh

RUN /opt/setup/build-zipapp.py


# 2026-10-23
FROM registry.access.redhat.com/ubi10-minimal:10.3-1794499233@sha256:fb2f7f857cc60d88e3fad19da505083a682ca4569d7b55a61f64aaa43641f741

ARG VERSION=2.0.0

# Need tar in the final image to perm the extraction of the installer ziapp.
RUN microdnf install tar -y --nodocs --setopt install_weak_deps=0 && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

USER 65532

WORKDIR /opt/ansible

COPY ansible.cfg ansible.cfg
COPY inventory/hosts.example.yml inventory/hosts.yml
COPY collections/ansible_collections/rhel collections/ansible_collections/rhel
COPY --from=builder /opt/rhel-cla-installer rhel-cla-installer

# License required by Red Hat preflight certification.
#   * LICENSE is the license for this project.
#   * licenses is the license for the ansible-galaxy collections used by this project.
COPY LICENSE licenses /licenses/

LABEL com.redhat.application=rhel-cla-installer
LABEL com.redhat.component=rhel-cla-installer
LABEL description="Red Hat Enterprise Linux (RHEL) command line assistant installer"
LABEL distribution-scope=private
LABEL io.k8s.description="Red Hat Enterprise Linux (RHEL) command line assistant"
LABEL io.k8s.display-name="Red Hat Enterprise Linux (RHEL) command line assistant installer"
LABEL io.openshift.tags="rhel,command-line-assistant,installer"
LABEL name="rhel-cla/installer-rhel10"
LABEL cpe="cpe:/a:redhat:rhel_cla:2.0::el10"
LABEL url="https://github.com/rhel-lightspeed/rhel-cla-installer"
LABEL vendor="Red Hat, Inc."
LABEL summary="Red Hat Enterprise Linux (RHEL) command line assistant installer"
LABEL konflux.additional-tags=$VERSION
LABEL version=$VERSION
