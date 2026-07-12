# CSI Snapshot Controller Design

**Date:** 2026-07-12
**Status:** Approved for implementation

## Problem

Longhorn already runs the CSI snapshotter sidecar on all four K3s clusters, but the Kubernetes CSI snapshot API and the common snapshot controller are missing. The sidecar therefore logs repeated discovery errors for the snapshot resources and Kubernetes cannot create or restore Longhorn snapshots through `VolumeSnapshot` objects.

The repository needs a dedicated Kubernetes component that installs the upstream snapshot API, runs the common controller, and provides Longhorn snapshot classes following the naming and default strategy of the existing Longhorn StorageClasses.

## Goals

- Add a dedicated `Kubernetes/62-CSI-SnapshotController` component.
- Use the official Kubernetes CSI external-snapshotter release `v8.5.0`.
- Install the component on `ADMIN01`, `APPS01`, `APPS02`, and `HOME01`.
- Keep `_SAMPLE` and all four private overlays structurally identical.
- Install three Longhorn `VolumeSnapshotClass` objects named `longhorn`, `longhorn-delete`, and `longhorn-retain`.
- Make only `longhorn-delete` the default snapshot class.
- Use server-side apply for every deployment command in the documentation and rollout.
- Verify a complete snapshot and restore cycle on every cluster.
- Confirm that existing workloads remain healthy after the rollout.

## Non-goals

- Do not change K3s, kube-vip, or the Longhorn Helm release.
- Do not deploy another CSI snapshotter sidecar. Longhorn already provides the driver-specific sidecar.
- Do not enable Volume Group Snapshot behavior or create a `VolumeGroupSnapshotClass`.
- Do not configure Longhorn backups to S3. The snapshot classes create in-cluster Longhorn snapshots.
- Do not modify existing application PVCs or create snapshots of production PVCs during validation.

## Upstream Version and Sources

The component uses the official `kubernetes-csi/external-snapshotter` tag `v8.5.0` for both the CRDs and controller manifests:

- `https://github.com/kubernetes-csi/external-snapshotter/client/config/crd?ref=v8.5.0`
- `https://github.com/kubernetes-csi/external-snapshotter/deploy/kubernetes/snapshot-controller?ref=v8.5.0`

The upstream `v8.5.0` controller manifest still references the `v8.4.0` controller image. The local Kustomize controller base must override it with `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`, which is the image published for the `v8.5.0` release.

The remote references are pinned to the exact `v8.5.0` release tag. No unpinned `master` or release branch is allowed.

## Architecture

The component has two deployment phases because custom resources cannot be applied reliably before the API server has established their CRDs.

### Phase 1: Snapshot CRDs

`base/crds` references the official upstream CRD Kustomization. The upstream bundle contains the three volume snapshot CRDs and the three volume group snapshot CRDs. The complete upstream bundle is retained so the API definitions and controller RBAC stay version-aligned. Volume Group Snapshot behavior remains disabled because no feature gate or group snapshot class is configured.

The deployment waits until every supplied CRD reports `Established=True` before continuing.

### Phase 2: Controller and Snapshot Classes

`base/controller` references the official upstream snapshot-controller Kustomization, pins the image to `v8.5.0`, and places namespaced resources in `kube-system`. The upstream deployment runs two replicas with leader election.

The component root base combines that controller with the Longhorn snapshot classes. Namespace transformation is kept inside the controller sub-base so it cannot add a namespace to cluster-scoped `VolumeSnapshotClass` objects.

Each overlay adds the standard repository labels without changing upstream selectors:

```yaml
app.kubernetes.io/component: storage-controller
app.kubernetes.io/instance: csi-snapshot-controller
app.kubernetes.io/name: csi-snapshot-controller
app.kubernetes.io/part-of: system-services
app.kubernetes.io/version: 8.5.0
```

## Longhorn Snapshot Classes

All three classes use the Longhorn CSI driver and create in-cluster snapshots:

```yaml
driver: driver.longhorn.io
parameters:
  type: snap
```

| Class | Deletion policy | Default | Purpose |
|---|---|---|---|
| `longhorn` | `Delete` | No | Neutral compatibility name used by Longhorn documentation and integrations |
| `longhorn-delete` | `Delete` | Yes | Default class, deletes the Longhorn snapshot with its Kubernetes snapshot object |
| `longhorn-retain` | `Retain` | No | Retains the Longhorn snapshot when its Kubernetes snapshot object is removed |

Only `longhorn-delete` receives:

```yaml
snapshot.storage.kubernetes.io/is-default-class: "true"
```

`longhorn` and `longhorn-delete` intentionally share the same driver behavior. Their separate names mirror the existing Longhorn StorageClass strategy while keeping the official compatibility name available.

## Repository Layout

```text
Kubernetes/62-CSI-SnapshotController/
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
    │   └── kustomization.yaml
    ├── admin01/
    │   └── kustomization.yaml
    ├── apps01/
    │   └── kustomization.yaml
    ├── apps02/
    │   └── kustomization.yaml
    └── home01/
        └── kustomization.yaml
```

There are no cluster-specific values. Separate overlays are still required to match the repository convention and make the deployed intent explicit for every cluster.

## Deployment Flow

Clusters are processed strictly in this order:

1. `ADMIN01`
2. `APPS01`
3. `APPS02`
4. `HOME01`

The complete deployment and validation for one cluster must finish before the next cluster starts.

For each cluster:

1. Confirm the context and current health.
2. Capture the existing Longhorn CSI snapshotter discovery error as the RED baseline.
3. Build and server-side apply `base/crds`.
4. Wait for all supplied CRDs to become established.
5. Build and run a server-side dry-run for the cluster overlay.
6. Server-side apply the cluster overlay.
7. Wait for both snapshot-controller replicas to become available.
8. Inspect controller and Longhorn CSI snapshotter logs.
9. Run the isolated snapshot and restore test.
10. Recheck nodes, Deployments, StatefulSets, DaemonSets, Pods, Longhorn volumes, and PVCs.

No deployment command may omit `--server-side`. `--force-conflicts` is not used automatically. Any ownership conflict must be inspected before deciding how to proceed.

## Validation Strategy

This change contains Kubernetes configuration only, so validation uses integration-level RED and GREEN evidence instead of application unit tests.

### Static Validation

- `kustomize build` succeeds for `base/crds` and all five overlays.
- The rendered controller image is exactly `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`.
- The rendered output contains exactly three `VolumeSnapshotClass` objects.
- Only `longhorn-delete` is marked as default.
- Every deployment example in the new README uses server-side apply.

### Live API and Controller Validation

- All upstream CRDs report `Established=True`.
- `snapshot.storage.k8s.io/v1` resources are discoverable.
- `deployment/snapshot-controller` is `2/2` Available in `kube-system`.
- The controller logs contain no repeated API discovery, RBAC, leader election, or reconciliation errors.
- New Longhorn `csi-snapshotter` log entries no longer report missing snapshot resource APIs.

### Snapshot and Restore Test

Use a temporary namespace and test resources only:

1. Create a small PVC using the `longhorn-delete` StorageClass.
2. Mount it in a temporary Pod and write a unique marker file.
3. Create a `VolumeSnapshot` without an explicit class name to verify default-class selection.
4. Wait for `readyToUse: true` and confirm that Kubernetes selected `longhorn-delete`.
5. Restore a second PVC from the snapshot.
6. Mount the restored PVC in a second Pod and verify the marker exactly.
7. Delete the test resources and verify that no test PVC, PV, VolumeAttachment, VolumeSnapshotContent, or Longhorn volume remains.

The `longhorn-retain` class is validated from its rendered and live policy. The functional smoke test does not use it because a retain-policy test would intentionally leave storage data behind.

## Error Handling and Rollback

- If an upstream remote cannot be fetched, stop before changing the cluster.
- If a CRD does not become established, stop before applying the controller and classes.
- If server-side dry-run fails, do not run the live apply.
- If the controller does not become ready, collect events and logs and do not continue to the next cluster.
- If the snapshot or restore test fails, keep the temporary resources long enough to collect diagnostics, then remove only those test resources after the cause is understood.
- Do not delete snapshot CRDs automatically during rollback. Removing CRDs can delete snapshot API objects and is therefore outside an automatic rollback.
- A controller rollback restores the previously applied controller manifest while leaving established CRDs and existing snapshot objects intact.

## Acceptance Criteria

The change is complete only when all of the following are true on all four clusters:

- The six pinned upstream snapshot CRDs are established.
- Two `snapshot-controller:v8.5.0` replicas are available.
- `longhorn`, `longhorn-delete`, and `longhorn-retain` exist.
- `longhorn-delete` is the only default `VolumeSnapshotClass`.
- A temporary Longhorn PVC can be snapshotted and restored with identical data.
- No temporary test storage objects remain.
- Longhorn CSI snapshotter logs no longer show missing snapshot API errors.
- Existing cluster workloads and Longhorn volumes remain healthy.
- `_SAMPLE`, `admin01`, `apps01`, `apps02`, and `home01` render successfully.
- The README documents only server-side deployment commands.

## References

- [Kubernetes CSI external-snapshotter v8.5.0](https://github.com/kubernetes-csi/external-snapshotter/releases/tag/v8.5.0)
- [Kubernetes CSI external-snapshotter usage](https://github.com/kubernetes-csi/external-snapshotter/tree/v8.5.0)
- [Longhorn CSI Snapshot Support](https://longhorn.io/docs/1.12.0/snapshots-and-backups/csi-snapshot-support/enable-csi-snapshot-support/)
- [Kubernetes Volume Snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/)
