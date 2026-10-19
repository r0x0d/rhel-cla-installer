# ──────────────────────────────────────────────────────────────────────────────
# builder: Hummingbird Python 3.12 builder image.
#
# Has bash, dnf/dnf5, and pip — everything needed, including `dnf install` on
# s390x for gcc/libffi-devel/openssl-devel/python3-devel/rust-toolset.
# This stage is ephemeral; only /opt/rhel-cla-installer is copied out.
# ──────────────────────────────────────────────────────────────────────────────
FROM registry.access.redhat.com/hi/python:3.12-builder@sha256:d7e47ff8d9d9b612eaefb5925fcfd36e38c5ce622dc7f0f0508b4fdd090a1510 AS builder

USER 0

# Install ansible-core so ansible-galaxy is available. The upper bound matches
# requirements.in; the exact version is frozen in requirements-3.12.txt.
COPY requirements/*.txt      /opt/setup/
RUN pip3 install --no-cache-dir -r /opt/setup/requirements-3.12.txt

# Download galaxy collections — ansible-galaxy writes to
COPY requirements/requirements.yml /opt/setup/requirements.yml
RUN ansible-galaxy collection install -r /opt/setup/requirements.yml -p /opt/setup/collections

# Add the local rhel namespace alongside the downloaded collections.
COPY collections/ansible_collections/rhel \
     /opt/setup/collections/ansible_collections/rhel

COPY scripts/build-zipapp.py /opt/setup/

RUN /opt/setup/build-zipapp.py


FROM registry.access.redhat.com/ubi10-minimal:10.2-1791784796@sha256:9712ae522acef7e90c571280b4faf69614b59395448d6bfb1c780c3bbf168218

ARG VERSION=2.0.0

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
LABEL cpe="cpe:/a:redhat:rhel_cla:1.0::el10"
LABEL url="https://github.com/rhel-lightspeed/rhel-cla-installer"
LABEL vendor="Red Hat, Inc."
LABEL summary="Red Hat Enterprise Linux (RHEL) command line assistant installer"
LABEL konflux.additional-tags=$VERSION
LABEL version=$VERSION
