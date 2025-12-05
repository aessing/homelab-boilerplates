# Nebula-Sync

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Nebula-Sync](https://github.com/lovelaze/nebula-sync), a tool for synchronizing Pi-hole configurations across multiple instances.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Nebula-Sync/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── deployment.yaml           # Nebula-Sync deployment
│       ├── namespace.yaml            # Kubernetes namespace
│       └── resource-quota.yaml       # Namespace resource quotas
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **Configuration Sync**: Synchronize Pi-hole settings across instances
- **Gravity Sync**: Keep blocklists in sync
- **Custom Lists**: Sync whitelists and blacklists
- **Scheduled Sync**: Periodic synchronization via CronJob or deployment

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- Multiple [Pi-hole](../Pi-hole/) instances deployed
- Pi-hole API access (password or API token)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-nebula-sync-replicas.env`** - Pi-hole instance credentials:

```dotenv
PRIMARY_HOST=http://pihole-primary.pihole.svc.cluster.local
PRIMARY_PASSWORD=<primary-pihole-password>
SECONDARY_HOSTS=http://pihole-secondary.pihole.svc.cluster.local
SECONDARY_PASSWORD=<secondary-pihole-password>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `config.yaml` | Sync configuration options |
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 4. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply -f -
```

## Configuration

### Sync Configuration

The `config.yaml` patch controls what gets synchronized:

```yaml
- op: replace
  path: /spec/template/spec/containers/0/env
  value:
    - name: SYNC_GRAVITY
      value: "true"
    - name: SYNC_CUSTOM_LIST
      value: "true"
    - name: SYNC_WHITELIST
      value: "true"
    - name: SYNC_BLACKLIST
      value: "true"
    - name: SYNC_INTERVAL
      value: "3600"
```

### Sync Options

| Option | Description |
|--------|-------------|
| `SYNC_GRAVITY` | Sync gravity database (blocklists) |
| `SYNC_CUSTOM_LIST` | Sync custom DNS entries |
| `SYNC_WHITELIST` | Sync whitelist entries |
| `SYNC_BLACKLIST` | Sync blacklist entries |
| `SYNC_INTERVAL` | Seconds between syncs |

### Multiple Secondary Instances

To sync to multiple secondary Pi-holes, separate hosts with commas:

```dotenv
SECONDARY_HOSTS=http://pihole-2:80,http://pihole-3:80,http://pihole-4:80
```

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n nebula-sync
kubectl get deployment nebula-sync -n nebula-sync
```

### View sync logs

```bash
kubectl logs -n nebula-sync -l app.kubernetes.io/name=nebula-sync
```

### Manual sync trigger

Restart the deployment to trigger an immediate sync:

```bash
kubectl rollout restart deployment nebula-sync -n nebula-sync
```

### Check Pi-hole connectivity

```bash
kubectl exec -it -n nebula-sync deployment/nebula-sync -- curl http://pihole-primary.pihole.svc.cluster.local/admin/api.php
```

### Verify sync status

Check Pi-hole admin interfaces to verify configurations match across instances.

## Related Resources

- [Nebula-Sync GitHub](https://github.com/lovelaze/nebula-sync)
- [Pi-hole Documentation](https://docs.pi-hole.net/)
- [Pi-hole API](https://discourse.pi-hole.net/t/pi-hole-api/1863)
- [Kustomize Documentation](https://kustomize.io/)
