FROM registry.access.redhat.com/hi/python:3.12-builder AS builder

USER 0

COPY requirements/*.txt      /opt/setup/

# Galaxy collections: build-zipapp.py installs them into the collections
# layout with ansible-galaxy. Konflux hermetic builds install the tarballs
# prefetched by Hermeto's generic fetcher (requirements/artifacts.lock.yaml)
# with --offline; local builds install the collections pinned in
# requirements/requirements.yml from galaxy.ansible.com. The pip
# requirements are installed by build-zipapp.py into dedicated virtual
# environments; under hermetic builds they are served from the prefetched
# dependency store (PIP_FIND_LINKS/PIP_NO_INDEX).
COPY requirements/requirements.yml /opt/setup/requirements.yml

# Add the local rhel namespace alongside the galaxy collections.
COPY collections/ansible_collections/rhel \
     /opt/setup/collections/ansible_collections/rhel

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


FROM registry.access.redhat.com/ubi10-minimal:10.2-1791784796

ARG VERSION=2.0.0

# Need tar in the final image to perm the extraction of the installer ziapp.
RUN microdnf install tar -y --nodocs --setopt install_weak_deps=0 && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

USER 65532

WORKDIR /opt/ansible

COPY ansible.cfg ansible.cfg
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
LABEL cpe="cpe:/a:redhat:rhel_cla:1.0::el10"
LABEL url="https://github.com/rhel-lightspeed/rhel-cla-installer"
LABEL vendor="Red Hat, Inc."
LABEL summary="Red Hat Enterprise Linux (RHEL) command line assistant installer"
LABEL konflux.additional-tags=$VERSION
LABEL version=$VERSION
