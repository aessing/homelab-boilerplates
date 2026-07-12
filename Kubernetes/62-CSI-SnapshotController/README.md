# CSI Snapshot Controller

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder deploys the Kubernetes CSI snapshot CRDs and the common snapshot controller. Longhorn already provides the driver-specific CSI snapshotter sidecar.

## Prerequisites

- Kubernetes 1.25 or newer
- Longhorn with CSI snapshot support
- Kustomize with network access to fetch the pinned upstream manifests
- A kubeconfig context for the target cluster

## Components

- Official external-snapshotter CRDs pinned to `v8.5.0`
- Two common snapshot-controller replicas in `kube-system`
- Controller image pinned to `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`
- Three Longhorn `VolumeSnapshotClass` objects

The upstream CRD bundle also installs the Volume Group Snapshot CRDs. Group snapshot behavior remains disabled because no feature gate or `VolumeGroupSnapshotClass` is configured.

## Structure

```text
62-CSI-SnapshotController/
├── README.md
├── base/
│   ├── kustomization.yaml
│   ├── controller/
│   │   └── kustomization.yaml
│   ├── crds/
│   │   └── kustomization.yaml
│   └── resources/
│       └── volumesnapshotclass.yaml
└── overlay/
    ├── _SAMPLE/
    └── <cluster>/
```

## Longhorn Snapshot Classes

| Class | Deletion policy | Default | Purpose |
|---|---|---|---|
| `longhorn` | `Delete` | No | Compatibility name used by Longhorn documentation and integrations |
| `longhorn-delete` | `Delete` | Yes | Deletes the Longhorn snapshot with the Kubernetes snapshot object |
| `longhorn-retain` | `Retain` | No | Retains the Longhorn snapshot when the Kubernetes snapshot object is removed |

All classes use:

```yaml
driver: driver.longhorn.io
parameters:
  type: snap
```

`type: snap` creates an in-cluster Longhorn snapshot. It does not create an S3 backup.

## Deployment

CRDs must be established before applying the controller and snapshot classes.

Process clusters in this order and complete all checks before continuing:

1. `ADMIN01`
2. `APPS01`
3. `APPS02`
4. `HOME01`

The following example deploys the `admin01` overlay:

```bash
kustomize build base/crds | kubectl --context ADMIN01 apply --server-side -f -

kubectl --context ADMIN01 wait --for=condition=Established --timeout=120s \
  crd/volumesnapshotclasses.snapshot.storage.k8s.io \
  crd/volumesnapshotcontents.snapshot.storage.k8s.io \
  crd/volumesnapshots.snapshot.storage.k8s.io \
  crd/volumegroupsnapshotclasses.groupsnapshot.storage.k8s.io \
  crd/volumegroupsnapshotcontents.groupsnapshot.storage.k8s.io \
  crd/volumegroupsnapshots.groupsnapshot.storage.k8s.io

kustomize build overlay/admin01 | kubectl --context ADMIN01 apply --server-side --dry-run=server -f -
kustomize build overlay/admin01 | kubectl --context ADMIN01 apply --server-side -f -
```

Replace both the context and overlay together for the other clusters:

| Context | Overlay |
|---|---|
| `ADMIN01` | `admin01` |
| `APPS01` | `apps01` |
| `APPS02` | `apps02` |
| `HOME01` | `home01` |

## Verification

Check the snapshot API, controller, classes, and logs:

```bash
kubectl --context ADMIN01 api-resources --api-group=snapshot.storage.k8s.io
kubectl --context ADMIN01 -n kube-system rollout status deployment/snapshot-controller --timeout=180s
kubectl --context ADMIN01 -n kube-system get deployment snapshot-controller -o wide
kubectl --context ADMIN01 get volumesnapshotclass
kubectl --context ADMIN01 -n kube-system logs deployment/snapshot-controller --all-pods=true --tail=200
kubectl --context ADMIN01 -n longhorn-system logs deployment/csi-snapshotter -c csi-snapshotter --all-pods=true --since=10m --tail=200
```

Expected results:

- Six snapshot CRDs are established.
- The controller Deployment is `2/2` Available.
- The controller image is `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`.
- `longhorn-delete` is the only default `VolumeSnapshotClass`.
- Controller and Longhorn CSI snapshotter logs contain no new missing-API, RBAC, leader-election, or reconciliation errors.

## Example VolumeSnapshot

This example uses the default `longhorn-delete` class because `volumeSnapshotClassName` is omitted:

```yaml
---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: example
  namespace: default
spec:
  source:
    persistentVolumeClaimName: example
```

Apply examples with server-side apply:

```bash
kubectl --context ADMIN01 apply --server-side -f volumesnapshot.yaml
```

Wait until the snapshot is ready:

```bash
kubectl --context ADMIN01 -n default wait \
  --for=jsonpath='{.status.readyToUse}'=true \
  volumesnapshot/example \
  --timeout=300s
```

## Troubleshooting

### Snapshot API is missing

Apply `base/crds` first and wait for every CRD to become established. Do not apply the controller overlay in the same first request as the CRDs.

### Controller does not become ready

Inspect the Deployment, events, and logs:

```bash
kubectl --context ADMIN01 -n kube-system describe deployment snapshot-controller
kubectl --context ADMIN01 -n kube-system get events --sort-by=.lastTimestamp
kubectl --context ADMIN01 -n kube-system logs deployment/snapshot-controller --all-pods=true --tail=200
```

### More than one default class

Exactly one class for `driver.longhorn.io` may have the default annotation set to `true`:

```bash
kubectl --context ADMIN01 get volumesnapshotclass -o custom-columns=NAME:.metadata.name,DRIVER:.driver,DEFAULT:.metadata.annotations.snapshot\.storage\.kubernetes\.io/is-default-class
```

## References

- [Kubernetes CSI external-snapshotter v8.5.0](https://github.com/kubernetes-csi/external-snapshotter/releases/tag/v8.5.0)
- [Longhorn CSI Snapshot Support](https://longhorn.io/docs/1.12.0/snapshots-and-backups/csi-snapshot-support/enable-csi-snapshot-support/)
- [Kubernetes Volume Snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/)
