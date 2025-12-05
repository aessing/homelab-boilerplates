# Home Assistant

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Home Assistant](https://www.home-assistant.io/), the open-source home automation platform.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
HomeAssistant/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       └── resource-quota.yaml       # Namespace resource quotas
├── components/
│   ├── _database/                    # PostgreSQL database (CNPG)
│   │   └── resources/
│   │       ├── cluster.yaml          # CNPG cluster definition
│   │       ├── database.yaml         # Database definitions
│   │       ├── objectstore.yaml      # Backup object storage
│   │       └── scheduledbackup.yaml  # Backup schedule
│   ├── _editor/                      # VS Code editor (code-server)
│   ├── _homeassistant/               # Home Assistant core
│   │   └── resources/
│   │       └── multus.yaml           # Multi-network configuration
│   └── _mqtt/                        # Mosquitto MQTT broker
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **Home Automation**: Control and automate smart home devices
- **Multi-Network Support**: Multus CNI for IoT network access
- **MQTT Broker**: Integrated Mosquitto for device communication
- **Code Editor**: VS Code Server for configuration editing
- **PostgreSQL Backend**: Highly available database via CloudNativePG
- **Automated Backups**: Scheduled database backups to S3
- **TLS Encryption**: Secure connections via cert-manager

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [CloudNativePG Operator](https://cloudnative-pg.io/documentation/current/installation_upgrade/) installed
- [cert-manager](https://cert-manager.io/) installed and configured
- [Traefik](https://traefik.io/) ingress controller
- [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni) for multi-network support
- [MetalLB](https://metallb.universe.tf/) for LoadBalancer services (MQTT)
- S3-compatible object storage for backups (optional but recommended)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-homeassistant-db-user.env`** - Database credentials:

```dotenv
username=homeassistant
password=<your-secure-password>
```

**`secrets/secret-homeassistant-db-objectstore.env`** - S3 backup credentials:

```dotenv
ACCESS_KEY_ID=<your-access-key-id>
ACCESS_KEY_NAME=<your-access-key-name>
ACCESS_SECRET_KEY=<your-secret-key>
```

**`secrets/secret-mqtt-user.env`** - MQTT user credentials:

```dotenv
MQTT_USERNAME=homeassistant
MQTT_PASSWORD=<your-secure-password>
```

**`secrets/secret-mqtt-acl.env`** - MQTT access control list:

```dotenv
# ACL configuration for Mosquitto
```

**`secrets/secret-editor-user.env`** - Code editor credentials:

```dotenv
PASSWORD=<your-secure-password>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate-homeassistant.yaml` | TLS certificate for Home Assistant |
| `certificate-editor.yaml` | TLS certificate for code editor |
| `certificate-mqtt.yaml` | TLS certificate for MQTT |
| `homeassistant-db.yaml` | Database instance count, PostgreSQL version, storage |
| `homeassistant-db-objectstore.yaml` | S3 bucket and endpoint for backups |
| `homeassistant-db-schedule.yaml` | Backup schedule (cron format) |
| `ingressroute-homeassistant.yaml` | External hostname for Home Assistant |
| `ingressroute-editor.yaml` | External hostname for code editor |
| `multus-homeassistant.yaml` | Network interface for IoT access |
| `network-policy.yaml` | Client IP ranges for access |
| `pvc-homeassistant.yaml` | Home Assistant storage size |
| `pvc-editor.yaml` | Code editor storage size |
| `resource-quota.yaml` | Namespace pod and PVC limits |
| `service-mqtt.yaml` | MQTT LoadBalancer IP address |

### 4. Configure Multus

Edit the `multus-homeassistant.yaml` patch to configure the secondary network interface:

```yaml
- op: replace
  path: /spec/config
  value: '{
    "cniVersion": "0.3.1",
    "type": "ipvlan",
    "master": "eth0",
    "mode": "l2",
    "ipam": {
      "type": "static",
      "addresses": [{"address": "192.168.1.100/24", "gateway": "192.168.1.1"}],
      "routes": [{"dst": "192.168.1.0/24"}]
    }
  }'
```

### 5. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply -f -
```

## Components

This application uses modular components:

| Component | Description |
|-----------|-------------|
| `_database` | PostgreSQL database via CloudNativePG |
| `_editor` | VS Code Server for config editing |
| `_homeassistant` | Home Assistant core with Multus networking |
| `_mqtt` | Mosquitto MQTT broker |

Enable components in your overlay's `kustomization.yaml`:

```yaml
components:
  - ../../components/_database
  - ../../components/_homeassistant
  - ../../components/_mqtt
  - ../../components/_editor
```

## Configuration

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate-*.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate-*.yaml`, `ingressroute-*.yaml` | External domain names |
| `###INSTANCE_COUNT(3)###` | `homeassistant-db.yaml` | Number of database instances |
| `###PGSQL_VERSION###` | `homeassistant-db.yaml` | PostgreSQL version (16, 17, 18) |
| `###PVC_SIZE###` | `homeassistant-db.yaml` | Database storage size |
| `###CLUSTER_CIDR###` | `network-policy.yaml` | Allowed client CIDR |
| `###IP_ADDRESS_FOR_MQTT_SERVICE###` | `service-mqtt.yaml` | MetalLB IP for MQTT |

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n homeassistant
kubectl get statefulset -n homeassistant
```

### View application logs

```bash
kubectl logs -n homeassistant -l app.kubernetes.io/name=homeassistant
```

### Check database status

```bash
kubectl get cluster -n homeassistant
kubectl cnpg status homeassistant-database -n homeassistant
```

### Check MQTT broker

```bash
kubectl logs -n homeassistant -l app.kubernetes.io/name=mosquitto
```

### Access code editor

Navigate to the editor URL configured in your ingress route to edit Home Assistant configuration files.

## Related Resources

- [Home Assistant Documentation](https://www.home-assistant.io/docs/)
- [Home Assistant Integrations](https://www.home-assistant.io/integrations/)
- [Mosquitto Documentation](https://mosquitto.org/documentation/)
- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/)
- [Multus CNI Documentation](https://github.com/k8snetworkplumbingwg/multus-cni/blob/master/docs/README.md)
- [Kustomize Documentation](https://kustomize.io/)
