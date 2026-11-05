# Red Hat Enterprise Linux Command Line Assistant Installer #

This is the installer for the self-managed RHEL CLA. It supports local and remote installations. OpenShift support is still in development.

# Getting Started #

Follow these instructions to get started using the RHEL CLA installer.

See the [contributing] docs for information on project development and maintenance.

## Prerequisites ##

- RHEL 9.5 or later
- Python 3.11 or later
- [`podman`] 5 or later
- `tar`
- A [Red Hat Offline Knowledge Portal key][rhokp_key]
- 30GB of free disk space for the Red Hat Offline Knowledge Portal.
- Valid container registry login credentials in `/etc/containers/auth.json`.
- `sudo` permissions on all systems where RHEL CLA will be installed. This includes when installing locally.

Create the container registry login credentials. This needs to be done on both local and remote systems, or the auth file can be generated once and copied to remote systems.

```
sudo podman login --authfile /etc/containers/auth.json registry.redhat.io
```

See the [providers documentation] for provider specific configuration. The provider must be setup and available before running the installer.


# Local Installation #

1. Create a directory for the installer and its configuration.

    ```
    mkdir rhel-cla-installer
    cd rhel-cla-installer
    ```

1. Extract the installer from the container image in order to run it against `localhost`.

    ```
    export IMAGE=quay.io/redhat-user-workloads/rhel-lightspeed-tenant/rhel-cla-installer
    podman run --rm -i --entrypoint sh "$IMAGE" -c 'tar -cf - ansible.cfg rhel-cla-installer' | tar -xf -
    ```

    If you have not yet created an inventory, extract the example inventory as a starting point. This will overwrite existing inventory without warning.

    ```
    podman run --rm -i --entrypoint sh "$IMAGE" -c 'tar -cf - inventory' | tar -xf -
    ```

1. Update the variables in `inventory/hosts.yml`, such as `okp_access_key`. Some variables depend on the external provider.

1. Run the installer.

    **Note**: Do not run the installer using `sudo`. Run it as a normal account with `sudo` privileges.

    If a password is required for `sudo`, add the `-K` option and enter the password when prompted.

    ```
    ./rhel-cla-installer rhel.cla.local
    ```

    By default, the installer uses `/usr/bin/env python3`. If that is not Python 3.11 or later, specify the executable used to run the installer.

    ```
    python3.11 rhel-cla-installer rhel.cla.local
    ```

    Adjust verbosity by adding `-v`. More v's give more verbosity.

## Verify Installation ##

Check the pod and container status.

```
sudo systemctl status rhel-cla-pod.service
sudo systemctl status rhel-knowledge-bridge.service
sudo systemctl status rh-offline-knowledge-portal.service
sudo systemctl status lightspeed-stack.service
```

Look at logs in the running containers.

```
sudo journalctl -f -u lightspeed-stack -u rhel-knowledge-bridge -u rh-offline-knowledge-portal
```

Test the local API.

```
curl http://localhost:8080/api/lightspeed/liveness
```

## Uninstall ##

Run `./rhel-cla-installer rhel.cla.local_uninstall`

This will keep container images on the system by default. To remove container images, set `remove_images=yes`

```
./rhel-cla-installer rhel.cla.local_uninstall -e remove_images=yes
```

## Upgrade ##

See the [upgrading] documentation for details on how to upgrade.

# Deploy on OpenShift #

Example [templates] for deploying on OpenShift are available. Copy `openshift/params.example` to `openshift/params` and provide values as appropriate.

### Database ###

A template is provided to create a PostgreSQL database if needed. An existing PostgreSQL database can be used. Provide connection details in a secret with the following keys:

- `db.host`
- `db.port`
- `db.name`
- `db.user`
- `db.password`

Set `POSTGRES_SECRET_NAME` to the secret name in `openshift/params`.

```
cd openshift
oc process --param-file params --ignore-unknown-parameters -f postgresql.yml | oc apply -f -
```

### Authentication ###

The template uses [token authentication] by default and will generate a new key by default. To retrieve it, run `oc get configmap lightspeed-stack-config -o jsonpath='{.data.lightspeed-stack\\.yaml}'` in the deployment namespace and find the `api_key` value under `authentication`.

Set `API_KEY` to a value in `openshift/params` to choose your own key.

To use the key, set the `Authorization: Bearer ${API_KEY}` header when interacting with the API directly, or set it in your LLM client.

[JWK token authentication] may be appropriate in enterprise deployments.


### Provider Secret ###

Credentials used to authenticate to an inference provider must be configured as secrets and made available. For example, Vertex AI expects the service account JSON to be stored in a secret name `vertexai` in the `credentials_json` key. Override the secret name by setting `VERTEX_AI_SECRET_NAME`.

### Deploy ###

Once any customizations are made and the correct parameters are provided, process and apply the application templates. The PostgreSQL template is optional and should already be applied if necessary.

```
cd openshift
for template in redhat-okp rhel-knowledge-bridge lightspeed-stack-vertex; do
    oc process --param-file params --ignore-unknown-parameters -f "${template}.yml" | oc apply -f -
done
```

# Client Configurations #

## Goose (goose-redhat) ##


1. Add an endpoint to the `[backend]` section of `/etc/xdg/goose-proxy/config.toml` and update the timeout:

    ```toml
    timeout = 300
    endpoint = "http://127.0.0.1:8080/v1"
    ```

1. Restart the proxy.

    ```
    sudo systemctl restart goose-proxy
    ```

[`podman`]: https://podman.io/
[rhokp_key]: https://access.redhat.com/offline/access/
[contributing]: docs/contributing.md
[upgrading]: docs/upgrading.md
[providers documentation]: docs/providers.md
[templates]: openshift/
[token authentication]: https://github.com/lightspeed-core/lightspeed-stack/blob/main/docs/auth/api-key-token.md
[JWK token authentication]: https://github.com/lightspeed-core/lightspeed-stack/blob/main/docs/auth/jwk-token.md
