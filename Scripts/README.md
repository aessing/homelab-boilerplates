# Helper Scripts

> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains utility scripts for managing and monitoring Kubernetes clusters, particularly for Longhorn storage management.

## Contents

```text
Scripts/
├── checkVolumes.sh           # Check PVC usage across namespaces
└── setLonghornTrimOnly.sh    # Configure Longhorn volume trim jobs
```

## Prerequisites

- `kubectl` configured to access your Kubernetes cluster
- `jq` installed (for JSON parsing in `checkVolumes.sh`)
- Appropriate RBAC permissions to access pods and volumes

## Scripts

### checkVolumes.sh

Checks the disk usage of Persistent Volume Claims (PVCs) across all relevant Kubernetes namespaces.

#### What It Does

- Iterates through all namespaces (excluding system namespaces)
- Finds pods that have PVCs attached
- Executes `df -h` inside each container to show disk usage
- Reports storage utilization for each mounted volume

#### Excluded Namespaces

The following system namespaces are automatically excluded:

- `certmgr-system`
- `kube-node-lease`
- `kube-public`
- `kube-system`
- `longhorn-system`
- `metallb-system`
- `multus-system`
- `reloader-system`
- `traefik-system`

#### Usage

```bash
./checkVolumes.sh
```

#### Example Output

```text
🔍 Searching for pods with PVCs in all relevant namespaces...
📂 Namespace: postgres
➡️  Pod with PVC: postgres-database-1
  📦 Container: postgres
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda        16G   2.1G   14G  13% /var/lib/postgresql/data
```

---

### setLonghornTrimOnly.sh

Configures a Longhorn volume to use only the weekly trim recurring job instead of the default recurring job group.

#### Description

1. Adds the label `recurring-job-group.longhorn.io/longhorn-job-trim-weekly=enabled` to the specified volume
2. Removes the label `recurring-job-group.longhorn.io/default` from the volume

This is useful when you want to:

- Disable default Longhorn recurring jobs (like snapshots or backups) for specific volumes
- Only run periodic TRIM operations to reclaim unused space
- Reduce snapshot/backup overhead for non-critical volumes

#### Syntax

```bash
./setLonghornTrimOnly.sh <volume-name>
```

#### Example

```bash
./setLonghornTrimOnly.sh pvc-abc12345-6789-0123-4567-890abcdef012
```

#### Sample Output

```text
===============================================
🚀 Longhorn Volume Label Setter
===============================================

🔖 Setting label 'recurring-job-group.longhorn.io/longhorn-job-trim-weekly=enabled' on volume pvc-abc12345...
volume.longhorn.io/pvc-abc12345-6789-0123-4567-890abcdef012 labeled

🧹 Removing label 'recurring-job-group.longhorn.io/default' from volume pvc-abc12345...
volume.longhorn.io/pvc-abc12345-6789-0123-4567-890abcdef012 unlabeled

✅ All done! Labels updated for volume pvc-abc12345.
```

#### Finding Volume Names

To find Longhorn volume names:

```bash
# List all Longhorn volumes
kubectl get volumes -n longhorn-system

# List volumes with their associated PVCs
kubectl get volumes -n longhorn-system -o custom-columns=NAME:.metadata.name,PVC:.status.kubernetesStatus.pvcName,NAMESPACE:.status.kubernetesStatus.namespace
```

## Making Scripts Executable

Before running the scripts, ensure they are executable:

```bash
chmod +x checkVolumes.sh setLonghornTrimOnly.sh
```

## Related Resources

- [Longhorn Documentation](https://longhorn.io/docs/)
- [Longhorn Recurring Jobs](https://longhorn.io/docs/latest/snapshots-and-backups/scheduling-backups-and-snapshots/)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
