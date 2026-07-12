# CSI Snapshot Controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and deploy the Kubernetes CSI snapshot API, common snapshot controller, and three Longhorn snapshot classes on all four K3s clusters.

**Architecture:** Use the official `kubernetes-csi/external-snapshotter` `v8.5.0` Kustomize resources. Apply CRDs first, wait for API discovery, then apply the controller and snapshot classes through cluster overlays. Validate each cluster with an isolated Longhorn snapshot and restore test before continuing.

**Tech Stack:** Kubernetes 1.36, K3s, Kustomize 5.8.1, server-side apply, Longhorn 1.12.0, CSI external-snapshotter 8.5.0

## Global Constraints

- Use external-snapshotter `v8.5.0` for CRDs and controller resources.
- Override the upstream controller image to `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`.
- Do not change K3s, kube-vip, or the Longhorn Helm release.
- Do not deploy another driver-specific CSI snapshotter sidecar.
- Do not enable Volume Group Snapshot behavior.
- Create `longhorn`, `longhorn-delete`, and `longhorn-retain`.
- Make only `longhorn-delete` the default `VolumeSnapshotClass`.
- Set `parameters.type: snap` on every Longhorn snapshot class.
- Keep `_SAMPLE`, `admin01`, `apps01`, `apps02`, and `home01` structurally identical.
- Preserve the repository ignore convention. Commit `_SAMPLE`, but keep `admin01`, `apps01`, `apps02`, and `home01` as local private overlays.
- Every deployment apply command must include `--server-side`.
- Do not use `--force-conflicts` without inspecting the ownership conflict first.
- Process clusters in this exact order: `ADMIN01`, `APPS01`, `APPS02`, `HOME01`.
- Finish deployment, logs, snapshot restore, cleanup, and health checks on one cluster before starting the next.
- Do not push Git changes.

---

### Task 1: Create the staged CSI snapshot base

**Files:**

- Create: `Kubernetes/62-CSI-SnapshotController/base/crds/kustomization.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/base/controller/kustomization.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/base/resources/volumesnapshotclass.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/base/kustomization.yaml`

**Interfaces:**

- Consumes: upstream Kustomize resources at tag `v8.5.0`
- Produces: a CRD-only build and a controller-plus-classes build

- [ ] **Step 1: Verify the component is absent**

Run:

```bash
kustomize build Kubernetes/62-CSI-SnapshotController/base/crds
```

Expected: non-zero exit with a message that the directory does not exist.

- [ ] **Step 2: Create the CRD base**

Create `Kubernetes/62-CSI-SnapshotController/base/crds/kustomization.yaml`:

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - https://github.com/kubernetes-csi/external-snapshotter/client/config/crd?ref=v8.5.0
```

- [ ] **Step 3: Create the controller base**

Create `Kubernetes/62-CSI-SnapshotController/base/controller/kustomization.yaml`:

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: kube-system

resources:
  - https://github.com/kubernetes-csi/external-snapshotter/deploy/kubernetes/snapshot-controller?ref=v8.5.0

images:
  - name: registry.k8s.io/sig-storage/snapshot-controller
    newTag: v8.5.0
```

- [ ] **Step 4: Create the Longhorn snapshot classes**

Create `Kubernetes/62-CSI-SnapshotController/base/resources/volumesnapshotclass.yaml`:

```yaml
---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: longhorn
  labels:
    app: longhorn
  annotations:
    snapshot.storage.kubernetes.io/is-default-class: "false"
driver: driver.longhorn.io
deletionPolicy: Delete
parameters:
  type: snap

---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: longhorn-delete
  labels:
    app: longhorn
  annotations:
    snapshot.storage.kubernetes.io/is-default-class: "true"
driver: driver.longhorn.io
deletionPolicy: Delete
parameters:
  type: snap

---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: longhorn-retain
  labels:
    app: longhorn
  annotations:
    snapshot.storage.kubernetes.io/is-default-class: "false"
driver: driver.longhorn.io
deletionPolicy: Retain
parameters:
  type: snap
```

- [ ] **Step 5: Compose the workload base**

Create `Kubernetes/62-CSI-SnapshotController/base/kustomization.yaml`:

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ./controller
  - ./resources/volumesnapshotclass.yaml
```

- [ ] **Step 6: Verify both bases render**

Run:

```bash
kustomize build Kubernetes/62-CSI-SnapshotController/base/crds | rg -c '^kind: CustomResourceDefinition$'
kustomize build Kubernetes/62-CSI-SnapshotController/base | rg 'image: registry.k8s.io/sig-storage/snapshot-controller:v8.5.0'
kustomize build Kubernetes/62-CSI-SnapshotController/base | rg -c '^kind: VolumeSnapshotClass$'
```

Expected:

- CRD count is `6`.
- The rendered controller image is `v8.5.0`.
- Snapshot class count is `3`.

---

### Task 2: Add all overlays and repository labels

**Files:**

- Create: `Kubernetes/62-CSI-SnapshotController/overlay/_SAMPLE/kustomization.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/overlay/admin01/kustomization.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/overlay/apps01/kustomization.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/overlay/apps02/kustomization.yaml`
- Create: `Kubernetes/62-CSI-SnapshotController/overlay/home01/kustomization.yaml`

**Interfaces:**

- Consumes: `Kubernetes/62-CSI-SnapshotController/base`
- Produces: five independently deployable, structurally identical overlays

- [ ] **Step 1: Verify the sample overlay is absent**

Run:

```bash
kustomize build Kubernetes/62-CSI-SnapshotController/overlay/_SAMPLE
```

Expected: non-zero exit with a message that the directory does not exist.

- [ ] **Step 2: Create every overlay with the exact content below**

Use this content in each of the five listed files:

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

buildMetadata:
  - managedByLabel
  - originAnnotations

labels:
  - includeSelectors: false
    pairs:
      app.kubernetes.io/component: storage-controller
      app.kubernetes.io/instance: csi-snapshot-controller
      app.kubernetes.io/name: csi-snapshot-controller
      app.kubernetes.io/part-of: system-services
      app.kubernetes.io/version: 8.5.0

resources:
  - ../../base
```

- [ ] **Step 3: Verify all overlays render**

Run:

```bash
for overlay in _SAMPLE admin01 apps01 apps02 home01; do
  kustomize build "Kubernetes/62-CSI-SnapshotController/overlay/${overlay}" >/dev/null || exit 1
done
```

Expected: exit code `0` with no build errors.

- [ ] **Step 4: Verify version and default-class policy in every overlay**

Run:

```bash
for overlay in _SAMPLE admin01 apps01 apps02 home01; do
  rendered="$(kustomize build "Kubernetes/62-CSI-SnapshotController/overlay/${overlay}")"
  test "$(printf '%s\n' "$rendered" | rg -c '^kind: VolumeSnapshotClass$')" = 3
  test "$(printf '%s\n' "$rendered" | rg -c 'snapshot.storage.kubernetes.io/is-default-class: "?true"?')" = 1
  printf '%s\n' "$rendered" | rg -q 'app.kubernetes.io/version: 8.5.0'
  printf '%s\n' "$rendered" | rg -q 'image: registry.k8s.io/sig-storage/snapshot-controller:v8.5.0'
done
```

Expected: exit code `0`.

---

### Task 3: Document two-phase server-side deployment and verification

**Files:**

- Create: `Kubernetes/62-CSI-SnapshotController/README.md`

**Interfaces:**

- Consumes: the CRD base and five cluster overlays
- Produces: the supported deployment, validation, troubleshooting, and example workflow

- [ ] **Step 1: Verify no README exists**

Run:

```bash
test ! -e Kubernetes/62-CSI-SnapshotController/README.md
```

Expected: exit code `0`.

- [ ] **Step 2: Write the README**

The README must contain these sections and exact operational rules:

```markdown
# CSI Snapshot Controller

This folder deploys the Kubernetes CSI snapshot CRDs and the common snapshot controller. Longhorn already supplies the driver-specific CSI snapshotter sidecar.

## Components

- Official external-snapshotter CRDs pinned to `v8.5.0`
- Two common snapshot-controller replicas in `kube-system`
- Controller image pinned to `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`
- `longhorn`, `longhorn-delete`, and `longhorn-retain` VolumeSnapshotClasses

## Longhorn Snapshot Classes

| Class | Deletion policy | Default |
|---|---|---|
| `longhorn` | `Delete` | No |
| `longhorn-delete` | `Delete` | Yes |
| `longhorn-retain` | `Retain` | No |

All classes use `driver.longhorn.io` with `parameters.type: snap`. They create in-cluster Longhorn snapshots, not S3 backups.

## Deployment

Install CRDs before the controller and classes:

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

Replace `ADMIN01` and `admin01` together for the other cluster overlays. Complete rollout and validation on one cluster before starting the next.

## Verification

```bash
kubectl --context ADMIN01 -n kube-system rollout status deployment/snapshot-controller --timeout=180s
kubectl --context ADMIN01 get volumesnapshotclass
kubectl --context ADMIN01 api-resources --api-group=snapshot.storage.k8s.io
kubectl --context ADMIN01 -n kube-system logs deployment/snapshot-controller --all-pods=true --tail=200
kubectl --context ADMIN01 -n longhorn-system logs daemonset/longhorn-csi-plugin -c csi-snapshotter --since=10m --tail=200
```

## Example VolumeSnapshot

```yaml
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

Omitting `volumeSnapshotClassName` selects the default `longhorn-delete` class.

## References

- https://github.com/kubernetes-csi/external-snapshotter/releases/tag/v8.5.0
- https://longhorn.io/docs/1.12.0/snapshots-and-backups/csi-snapshot-support/enable-csi-snapshot-support/
```

- [ ] **Step 3: Verify every apply command is server-side**

Run:

```bash
if rg --pcre2 'kubectl[^\n]*\bapply\b(?![^\n]*--server-side)' Kubernetes/62-CSI-SnapshotController/README.md; then
  exit 1
fi
```

Expected: exit code `0` and no matching lines.

---

### Task 4: Run complete static verification and commit the repository change

**Files:**

- Verify: `Kubernetes/62-CSI-SnapshotController/**`
- Verify: `docs/superpowers/specs/2026-07-12-csi-snapshot-controller-design.md`
- Verify: `docs/superpowers/plans/2026-07-12-csi-snapshot-controller.md`

**Interfaces:**

- Consumes: all repository artifacts from Tasks 1 through 3
- Produces: a locally verified component ready for server-side dry-run

- [ ] **Step 1: Build every target**

Run:

```bash
kustomize build Kubernetes/62-CSI-SnapshotController/base/crds >/dev/null
for overlay in _SAMPLE admin01 apps01 apps02 home01; do
  kustomize build "Kubernetes/62-CSI-SnapshotController/overlay/${overlay}" >/dev/null || exit 1
done
```

Expected: exit code `0`.

- [ ] **Step 2: Verify rendered invariants**

Run:

```bash
rendered="$(kustomize build Kubernetes/62-CSI-SnapshotController/overlay/_SAMPLE)"
test "$(printf '%s\n' "$rendered" | rg -c '^kind: VolumeSnapshotClass$')" = 3
test "$(printf '%s\n' "$rendered" | rg -c 'snapshot.storage.kubernetes.io/is-default-class: "?true"?')" = 1
printf '%s\n' "$rendered" | rg -q 'name: longhorn$'
printf '%s\n' "$rendered" | rg -q 'name: longhorn-delete$'
printf '%s\n' "$rendered" | rg -q 'name: longhorn-retain$'
printf '%s\n' "$rendered" | rg -q 'image: registry.k8s.io/sig-storage/snapshot-controller:v8.5.0'
```

Expected: exit code `0`.

- [ ] **Step 3: Check the patch and whitespace**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors and only the planned component and plan file are modified.

- [ ] **Step 4: Commit only the planned repository files**

Run:

```bash
git add Kubernetes/62-CSI-SnapshotController docs/superpowers/plans/2026-07-12-csi-snapshot-controller.md
git commit -m "feat: restore Kubernetes CSI snapshot support"
```

Expected: one commit containing the tracked base, `_SAMPLE`, README, and the updated implementation plan. Private overlays remain local and ignored.

---

### Task 5: Deploy and validate each cluster sequentially

**Files:**

- Deploy: `Kubernetes/62-CSI-SnapshotController/base/crds/kustomization.yaml`
- Deploy: `Kubernetes/62-CSI-SnapshotController/overlay/admin01/kustomization.yaml`
- Deploy: `Kubernetes/62-CSI-SnapshotController/overlay/apps01/kustomization.yaml`
- Deploy: `Kubernetes/62-CSI-SnapshotController/overlay/apps02/kustomization.yaml`
- Deploy: `Kubernetes/62-CSI-SnapshotController/overlay/home01/kustomization.yaml`

**Interfaces:**

- Consumes: the verified component from Task 4 and contexts `ADMIN01`, `APPS01`, `APPS02`, `HOME01`
- Produces: six established CRDs, two ready controller replicas, three classes, and a successful snapshot restore on every cluster

- [ ] **Step 1: Capture the RED baseline on all clusters**

Run read-only checks for each context before the first apply:

```bash
for context in ADMIN01 APPS01 APPS02 HOME01; do
  kubectl --context "$context" api-resources --api-group=snapshot.storage.k8s.io
  kubectl --context "$context" -n longhorn-system logs daemonset/longhorn-csi-plugin -c csi-snapshotter --since=10m --tail=100
done
```

Expected before installation: the snapshot API is absent and the Longhorn sidecar logs discovery errors for missing snapshot resources.

- [ ] **Step 2: Process one context and overlay at a time**

Use these exact pairs in order:

| Context | Overlay |
|---|---|
| `ADMIN01` | `admin01` |
| `APPS01` | `apps01` |
| `APPS02` | `apps02` |
| `HOME01` | `home01` |

For each pair, run:

```bash
kustomize build Kubernetes/62-CSI-SnapshotController/base/crds | kubectl --context CONTEXT apply --server-side -f -
kubectl --context CONTEXT wait --for=condition=Established --timeout=120s \
  crd/volumesnapshotclasses.snapshot.storage.k8s.io \
  crd/volumesnapshotcontents.snapshot.storage.k8s.io \
  crd/volumesnapshots.snapshot.storage.k8s.io \
  crd/volumegroupsnapshotclasses.groupsnapshot.storage.k8s.io \
  crd/volumegroupsnapshotcontents.groupsnapshot.storage.k8s.io \
  crd/volumegroupsnapshots.groupsnapshot.storage.k8s.io
kustomize build Kubernetes/62-CSI-SnapshotController/overlay/OVERLAY | kubectl --context CONTEXT apply --server-side --dry-run=server -f -
kustomize build Kubernetes/62-CSI-SnapshotController/overlay/OVERLAY | kubectl --context CONTEXT apply --server-side -f -
kubectl --context CONTEXT -n kube-system rollout status deployment/snapshot-controller --timeout=180s
```

Replace `CONTEXT` and `OVERLAY` with the exact pair from the table. Do not start the next pair until all remaining steps pass.

- [ ] **Step 3: Verify controller, classes, and logs on the current context**

Run:

```bash
kubectl --context CONTEXT -n kube-system get deployment snapshot-controller -o wide
kubectl --context CONTEXT -n kube-system get deployment snapshot-controller -o jsonpath='{.spec.template.spec.containers[?(@.name=="snapshot-controller")].image}{"\n"}'
kubectl --context CONTEXT get volumesnapshotclass
kubectl --context CONTEXT api-resources --api-group=snapshot.storage.k8s.io
kubectl --context CONTEXT -n kube-system logs deployment/snapshot-controller --all-pods=true --since=10m --tail=200
kubectl --context CONTEXT -n longhorn-system logs daemonset/longhorn-csi-plugin -c csi-snapshotter --since=5m --tail=200
```

Expected:

- Deployment is `2/2` Available.
- Image is exactly `registry.k8s.io/sig-storage/snapshot-controller:v8.5.0`.
- Exactly three classes exist and only `longhorn-delete` is default.
- No new missing-API, RBAC, leader-election, or reconciliation errors appear.

- [ ] **Step 4: Create isolated source data on the current context**

First ensure the test namespace is absent. If it already exists, stop and inspect it instead of deleting it.

Run after setting `context` to the current context name:

```bash
if kubectl --context "$context" get namespace csi-snapshot-test >/dev/null 2>&1; then
  echo "csi-snapshot-test already exists on ${context}"
  exit 1
fi

marker="csi-snapshot-${context}-20260712"

kubectl --context "$context" apply --server-side -f - <<EOF
---
apiVersion: v1
kind: Namespace
metadata:
  name: csi-snapshot-test
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: source
  namespace: csi-snapshot-test
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn-delete
  resources:
    requests:
      storage: 64Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: writer
  namespace: csi-snapshot-test
spec:
  restartPolicy: Never
  containers:
    - name: writer
      image: busybox:1.37.0
      command:
        - sh
        - -c
        - "printf '%s\\n' '${marker}' > /data/marker && sync && sleep 3600"
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: source
EOF

kubectl --context "$context" -n csi-snapshot-test wait --for=condition=Ready pod/writer --timeout=300s
source_marker="$(kubectl --context "$context" -n csi-snapshot-test exec writer -- cat /data/marker)"
test "$source_marker" = "$marker"
```

Expected: the writer Pod is Ready and `source_marker` equals `marker`.

- [ ] **Step 5: Snapshot through the default class**

Run:

```bash
kubectl --context "$context" apply --server-side -f - <<'EOF'
---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: source
  namespace: csi-snapshot-test
spec:
  source:
    persistentVolumeClaimName: source
EOF

kubectl --context "$context" -n csi-snapshot-test wait \
  --for=jsonpath='{.status.readyToUse}'=true \
  volumesnapshot/source \
  --timeout=300s

test "$(kubectl --context "$context" -n csi-snapshot-test get volumesnapshot source -o jsonpath='{.spec.volumeSnapshotClassName}')" = longhorn-delete
snapshot_content="$(kubectl --context "$context" -n csi-snapshot-test get volumesnapshot source -o jsonpath='{.status.boundVolumeSnapshotContentName}')"
test -n "$snapshot_content"
```

Expected: the snapshot becomes ready, Kubernetes selects `longhorn-delete`, and `snapshot_content` is non-empty.

- [ ] **Step 6: Restore and compare the marker**

Run:

```bash
kubectl --context "$context" apply --server-side -f - <<'EOF'
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: restored
  namespace: csi-snapshot-test
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn-delete
  dataSource:
    apiGroup: snapshot.storage.k8s.io
    kind: VolumeSnapshot
    name: source
  resources:
    requests:
      storage: 64Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: reader
  namespace: csi-snapshot-test
spec:
  restartPolicy: Never
  containers:
    - name: reader
      image: busybox:1.37.0
      command:
        - sh
        - -c
        - sleep 3600
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: restored
EOF

kubectl --context "$context" -n csi-snapshot-test wait --for=condition=Ready pod/reader --timeout=300s
restored_marker="$(kubectl --context "$context" -n csi-snapshot-test exec reader -- cat /data/marker)"
test "$restored_marker" = "$source_marker"
```

Expected: the marker matches the current context exactly.

- [ ] **Step 7: Clean only the temporary test resources**

Run:

```bash
source_pv="$(kubectl --context "$context" -n csi-snapshot-test get pvc source -o jsonpath='{.spec.volumeName}')"
restored_pv="$(kubectl --context "$context" -n csi-snapshot-test get pvc restored -o jsonpath='{.spec.volumeName}')"
test -n "$source_pv"
test -n "$restored_pv"

kubectl --context "$context" delete namespace csi-snapshot-test --wait=false
kubectl --context "$context" wait --for=delete namespace/csi-snapshot-test --timeout=300s
kubectl --context "$context" wait --for=delete "pv/${source_pv}" "pv/${restored_pv}" --timeout=300s
kubectl --context "$context" wait --for=delete "volumesnapshotcontent/${snapshot_content}" --timeout=300s
kubectl --context "$context" -n longhorn-system wait --for=delete "volume.longhorn.io/${source_pv}" "volume.longhorn.io/${restored_pv}" --timeout=300s

attachments="$(kubectl --context "$context" get volumeattachments -o jsonpath='{range .items[*]}{.spec.source.persistentVolumeName}{"\n"}{end}' | rg "^(${source_pv}|${restored_pv})$" || true)"
test -z "$attachments"
```

Expected: the namespace, both PVs, the snapshot content, both Longhorn volumes, and related VolumeAttachments are absent.

- [ ] **Step 8: Gate progression on current cluster health**

Run:

```bash
kubectl --context CONTEXT get nodes
kubectl --context CONTEXT get deployments,statefulsets,daemonsets -A
kubectl --context CONTEXT get pods -A
kubectl --context CONTEXT get pvc -A
kubectl --context CONTEXT -n longhorn-system get volumes.longhorn.io
```

Expected: nodes are Ready, workloads meet desired readiness, PVCs are Bound, and Longhorn volumes are Healthy. Investigate any new error before continuing.

---

### Task 6: Perform the final fleet audit and report

**Files:**

- Verify: Git working tree and the deployed resources on all four clusters

**Interfaces:**

- Consumes: all cluster results from Task 5
- Produces: a final table with deployment, API, class, restore, logs, and health results per cluster

- [ ] **Step 1: Recheck all acceptance criteria with fresh commands**

For every context, verify:

- six CRDs are Established
- controller Deployment is `2/2`
- controller image is `v8.5.0`
- the three expected snapshot classes exist
- only `longhorn-delete` is default
- no temporary test namespace or storage object remains
- no new missing snapshot API errors appear in Longhorn CSI snapshotter logs
- all nodes and existing workloads are ready
- all Longhorn volumes are healthy

- [ ] **Step 2: Verify the final repository state**

Run:

```bash
git status --short
git log -3 --oneline
git show --stat --oneline HEAD
```

Expected: no uncommitted implementation changes and no push performed.

- [ ] **Step 3: Produce the final result table**

Report one row per cluster with these columns:

| Cluster | CRDs | Controller | Snapshot classes | Snapshot restore | Logs | Cluster health |
|---|---|---|---|---|---|---|

State any remaining issue explicitly. Do not report success for a check that was not executed.
