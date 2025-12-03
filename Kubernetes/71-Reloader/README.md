# Reloader

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Reloader](https://github.com/stakater/Reloader) to a K3s cluster using the HelmChart CRD. Reloader is a Kubernetes controller that watches for changes in ConfigMaps and Secrets and automatically triggers rolling upgrades on Pods that use them.

## Prerequisites

- K3s cluster with HelmChart CRD support

## Structure

```text
71-Reloader/
├── base/
│   ├── kustomization.yaml
│   ├── patches/
│   │   └── target-namespace.yaml    # Sets target namespace for Helm deployment
│   ├── resources/
│   │   ├── namespace.yaml
│   │   ├── helmchart.yaml
│   │   └── helmchartconfig.yaml
│   └── transformers/
│       ├── helmchart.yaml
│       └── helmchartconfig.yaml
└── overlay/
    ├── _SAMPLE/                      # Template overlay
    └── <cluster>/                    # Environment-specific overlays
```

## Configuration

### Default Settings

The base HelmChartConfig includes the following defaults:

| Setting | Value | Description |
|---------|-------|-------------|
| `watchGlobally` | `true` | Watch all namespaces for changes |
| `enableHA` | `true` | Enable high availability mode |
| `replicas` | `2` | Number of Reloader replicas |
| `ignoreNamespaces` | System namespaces | Namespaces to ignore for reloading |
| `namespaceSelector` | `reloader.stakater.com/reload=enabled` | Label selector for namespaces |

### Ignored Namespaces

By default, Reloader ignores the following system namespaces:

- `certmgr-system`
- `kube-node-lease`
- `kube-public`
- `kube-system`
- `longhorn-system`
- `metallb-system`
- `multus-system`
- `reloader-system`
- `traefik-system`

## Overlay Configuration

Each overlay customizes:

| Patch | Description |
|-------|-------------|
| `version.yaml` | Reloader Helm chart version |

## Usage

1. Copy the `_SAMPLE` overlay to create an environment-specific configuration:

   ```bash
   cp -r overlay/_SAMPLE overlay/<cluster-name>
   ```

2. Update the patches with environment-specific values:
   - `version.yaml`: Set desired Reloader version

3. Deploy with Kustomize:

   ```bash
   kubectl apply -k overlay/<cluster-name>
   ```

## Enabling Reloading for a Namespace

To enable Reloader for a specific namespace, add the following label:

```bash
kubectl label namespace <namespace> reloader.stakater.com/reload=enabled
```

## Annotations for Deployments

Reloader supports several annotations to control reloading behavior:

### Watch All ConfigMaps and Secrets

```yaml
metadata:
  annotations:
    reloader.stakater.com/auto: "true"
```

### Watch Specific ConfigMaps

```yaml
metadata:
  annotations:
    configmap.reloader.stakater.com/reload: "configmap-name"
```

### Watch Specific Secrets

```yaml
metadata:
  annotations:
    secret.reloader.stakater.com/reload: "secret-name"
```

### Watch Multiple Resources

```yaml
metadata:
  annotations:
    configmap.reloader.stakater.com/reload: "configmap1,configmap2"
    secret.reloader.stakater.com/reload: "secret1,secret2"
```

## Useful Commands

### Check Reloader Status

```bash
kubectl -n reloader-system get pods
kubectl -n reloader-system logs -l app.kubernetes.io/name=reloader
```

### Verify Namespace Labels

```bash
kubectl get namespaces -l reloader.stakater.com/reload=enabled
```

### Check Reloader Metrics

```bash
kubectl -n reloader-system port-forward svc/reloader 9090:9090
```

## Troubleshooting

### Pods Not Restarting

1. Check if the namespace has the correct label:

   ```bash
   kubectl get namespace <namespace> --show-labels
   ```

2. Verify the deployment has the correct annotations:

   ```bash
   kubectl get deployment <deployment> -o yaml | grep -A5 annotations
   ```

3. Check Reloader logs:

   ```bash
   kubectl -n reloader-system logs -l app.kubernetes.io/name=reloader --tail=100
   ```

### Reloader Not Starting

1. Check pod status:

   ```bash
   kubectl -n reloader-system describe pods -l app.kubernetes.io/name=reloader
   ```

2. Verify HelmChart deployment:

   ```bash
   kubectl -n kube-system get helmcharts reloader
   ```

## References

- [Reloader GitHub Repository](https://github.com/stakater/Reloader)
- [Reloader Documentation](https://github.com/stakater/Reloader#readme)
- [Helm Chart](https://github.com/stakater/Reloader/tree/master/deployments/kubernetes/chart/reloader)
