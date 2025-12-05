# Multus CNI

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni) to a K3s cluster using the HelmChart CRD. Multus is a Container Network Interface (CNI) meta-plugin that enables attaching multiple network interfaces to Kubernetes pods.

## Prerequisites

- K3s cluster with HelmChart CRD support
- Ubuntu nodes with AppArmor installed

### Install Requirements

Before deploying Multus, run the requirements installation script on **all nodes**:

```bash
sudo ./11-install-requirements.sh
```

This script:

- Validates the environment (bash, systemctl, root, Ubuntu, AppArmor)
- Checks for the busybox AppArmor profile
- Adds required AppArmor permissions for Multus CNI binaries
- Reloads AppArmor configuration

## Structure

```text
81-Multus/
├── 11-install-requirements.sh    # AppArmor configuration script
├── base/
│   ├── kustomization.yaml
│   ├── patches/
│   │   └── target-namespace.yaml # Sets target namespace for Helm deployment
│   ├── resources/
│   │   ├── namespace.yaml
│   │   ├── helmchart.yaml
│   │   └── helmchartconfig.yaml
│   └── transformers/
│       ├── helmchart.yaml
│       └── helmchartconfig.yaml
└── overlay/
    ├── _SAMPLE/                  # Template overlay
    └── <cluster>/                # Environment-specific overlays
```

## Configuration

### Default Settings

The base HelmChartConfig includes the following K3S-specific settings:

| Setting | Value | Description |
|---------|-------|-------------|
| `config.fullnameOverride` | `multus` | Override the chart name |
| `config.cni_conf.confDir` | `/var/lib/rancher/k3s/agent/etc/cni/net.d` | CNI configuration directory |
| `config.cni_conf.binDir` | `/var/lib/rancher/k3s/data/cni/` | CNI binary directory |
| `config.cni_conf.kubeconfig` | `/var/lib/rancher/k3s/agent/etc/cni/net.d/multus.d/multus.kubeconfig` | Multus kubeconfig path |
| `config.cni_conf.multusAutoconfigDir` | `/var/lib/rancher/k3s/agent/etc/cni/net.d` | Multus autoconfig directory |
| `manifests.dhcpDaemonSet` | `true` | Enable DHCP DaemonSet for IPAM |

### AppArmor Permissions

The installation script adds the following permissions to `/etc/apparmor.d/busybox`:

```text
owner /etc/ld.so.cache** r,
owner /opt/cni/bin/** r,
owner /proc/** r,
owner /host/opt/cni/bin/** mrw,
owner /lib64/** mr,
owner /usr/lib64/** mr,
```

## Overlay Configuration

Each overlay customizes:

| Patch | Description |
|-------|-------------|
| `version.yaml` | Multus Helm chart version |

## Usage

1. Copy the `_SAMPLE` overlay to create an environment-specific configuration:

   ```bash
   cp -r overlay/_SAMPLE overlay/<cluster-name>
   ```

2. Update the patches with environment-specific values:
   - `version.yaml`: Set desired Multus version

3. Deploy with Kustomize:

   ```bash
   kustomize build overlay/<cluster-name> | kubectl apply --server-side -f -
   ```

## Creating NetworkAttachmentDefinitions

After Multus is deployed, create NetworkAttachmentDefinitions to define additional networks:

```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: my-macvlan-network
  namespace: default
spec:
  config: |
    {
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "eth0",
      "mode": "bridge",
      "ipam": {
        "type": "host-local",
        "subnet": "192.168.1.0/24",
        "rangeStart": "192.168.1.200",
        "rangeEnd": "192.168.1.250",
        "gateway": "192.168.1.1"
      }
    }
```

Reference it in your pods:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
  annotations:
    k8s.v1.cni.cncf.io/networks: my-macvlan-network
spec:
  containers:
  - name: my-container
    image: nginx
```

## Useful Commands

### Check Multus Status

```bash
kubectl -n multus-system get pods
kubectl -n multus-system get daemonsets
```

### Verify CNI Configuration

```bash
ls -la /var/lib/rancher/k3s/agent/etc/cni/net.d/
```

### Check DHCP Daemon

```bash
kubectl -n multus-system get pods -l app=dhcp-daemon
kubectl -n multus-system logs -l app=dhcp-daemon
```

## Troubleshooting

### Pod Creation Failures

1. Check if Multus pods are running:

   ```bash
   kubectl -n multus-system get pods
   ```

2. Check Multus logs:

   ```bash
   kubectl -n multus-system logs -l app=multus
   ```

3. Verify CNI configuration on nodes:

   ```bash
   ls -la /var/lib/rancher/k3s/agent/etc/cni/net.d/
   ```

### AppArmor Denials

1. Check AppArmor status:

   ```bash
   sudo aa-status | grep busybox
   ```

2. Re-run the setup script:

   ```bash
   sudo ./11-install-requirements.sh
   ```

3. Check system logs for denials:

   ```bash
   sudo dmesg | grep apparmor
   ```

### DHCP Issues

1. Verify DHCP daemon is running:

   ```bash
   kubectl -n multus-system get pods -l app=dhcp-daemon
   ```

2. Check DHCP logs:

   ```bash
   kubectl -n multus-system logs -l app=dhcp-daemon
   ```

## References

- [Multus CNI GitHub](https://github.com/k8snetworkplumbingwg/multus-cni)
- [RKE2 Multus Helm Chart](https://artifacthub.io/packages/helm/rke2-charts/rke2-multus/)
- [Multus Usage Guide](https://github.com/k8snetworkplumbingwg/multus-cni/blob/master/docs/how-to-use.md)
- [Kubernetes Network Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)
