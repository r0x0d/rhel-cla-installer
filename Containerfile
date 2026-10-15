# ──────────────────────────────────────────────────────────────────────────────
# builder: Hummingbird Python 3.12 builder image.
#
# Has bash, dnf/dnf5, and pip — everything needed, including `dnf install` on
# s390x for gcc/libffi-devel/openssl-devel/python3-devel/rust-toolset.
# This stage is ephemeral; only /opt/rhel-cla-installer is copied out.
# ──────────────────────────────────────────────────────────────────────────────
FROM registry.access.redhat.com/hi/python:3.12-builder AS builder

USER 0

COPY .konflux/pip/*.txt /opt/setup/
COPY scripts/build-zipapp.py /opt/setup/

RUN /opt/setup/build-zipapp.py


FROM registry.access.redhat.com/ubi10-minimal:10.2-1791784796

ARG VERSION=2.0.0

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
