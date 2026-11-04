# Providers #

Every inference provider is slightly different and may require different parameters. He are details for working with specific providers.

## Ramalama ##

Run `ramalama` using the desired model with a large context size. The `ramalama` listening interface must be reachable from Lightspeed Stack, which cannot access services listening on the loopback interface. You may bind to all interfaces with `0.0.0.0` or use a specific interface. List available interfaces with `ip -br address`.

List available models with `ramalama info --shortnames`.

In this example, `ramalama` is listening on the `podman0`, the bridge interface used by the RHEL CLA pod, with IP address `10.88.0.1`. This makes `ramalama` accessible to containers but not externally accessible.

```
ramalama serve granite:2b \
    --host 10.88.0.1 \
    --port 9010 \
    --ctx-size 65536
```

Get the model ID in order to update the Lightspeed Stack configuration.

```
ramalama models --url http://10.88.0.1:9010
```

Update the `default_model` value in `inventory/hosts.yml`.

```yaml
ramalama_config:
  default_model: [model ID]
```

Run the installer to update the configuration. This will restart the RHEL CLA pod if configuration changes are made.

```
rhel-cla-installer rhel.cla.local
```

**Note**: Lightspeed Stack only checks available models when it starts. If the models in `ramalama` changed, Lightspeed Stack needs to be restarted.

```
sudo systemctl restart lightspeed-stack
```


## Vertex AI ##

Create a `podman` secret that contains the service account credentials.

```
sudo podman secret create [secret name] [path to file]
```

Set the secret name, project_id, and location in the inventory variables.

**Note**: Model names must match the Goode SDK-native format exactly for model registration to succeed. For Vertex AI, the SDK returns the full resource-name format such as `publishers/google/models/gemini-2.5-flash`.

```yaml
vertex_config:
  default_model: publishers/google/models/gemini-2.5-flash
  credentials_secret_name: secret_name
  project_id: my_project
  location: global
```
