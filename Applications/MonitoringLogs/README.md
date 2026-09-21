# MonitoringLogs

Self-hosted log storage with Grafana Loki single-binary and a dedicated vmauth
proxy. Traefik provides HTTPS ingress, cert-manager manages the certificate, and
Longhorn provides persistent storage. Log collection is configured in
[MonitoringAgent](../MonitoringAgent/README.md).

## Contents

```text
base/                     Namespace, resource quota and network policies
components/
  _application/           Loki configuration, StatefulSet and Service
  _auth/                  vmauth Deployment, Service and authentication config
  _ingress/               Certificate and Traefik IngressRoutes
overlay/
  _SAMPLE/                Complete public template with sample data
    configs/              Loki settings and sample vmauth users
    generators/           ConfigMap and Secret generators
    patches/              Certificate, ingress, storage and quota settings
    secrets/              Non-sensitive placeholder credentials
    transformers/         Images, labels and replica counts
  <environment>/          Local configuration, ignored by Git
```

## Features

- One shared Loki tenant for cross-cluster queries.
- Separate bearer tokens for writers and Basic Auth for the read-only Grafana
  datasource. Writer count is configurable in the overlay.
- Allowlisted Loki APIs and HTTP methods, internal-IP ingress restrictions and
  default-deny NetworkPolicies. Loki has no direct external ingress.
- TSDB schema v13, filesystem object storage and 90-day retention.
- A 50 GiB initial `longhorn-retain` PVC with retained StatefulSet claims.
- Persistent chunks, index, cache, ingester WAL and compactor state on one PVC.
- Disabled Loki usage reporting and log deletion API.

This is a single-instance backend with replication factor one. Longhorn storage
replication does not provide application-level high availability. The filesystem
object store suits a small self-hosted installation but does not scale like an
object store. Log agents, Kubernetes Events and the Grafana datasource are not
part of this application and must be added separately.

## Prerequisites

- Kubernetes, `kubectl` and standalone `kustomize`.
- A CNI that enforces Kubernetes NetworkPolicies.
- Longhorn with the `longhorn-retain` StorageClass, or an equivalent class
  configured in the overlay. The class must support volume expansion.
- Traefik with its CRDs, the `websecure` entrypoint and cross-namespace
  middleware references enabled.
- The repository's `traefik-system/chain-default` middleware, including its
  RFC1918 allowlist. Patch the middleware and Pod selectors when names differ.
- cert-manager and a ready ClusterIssuer. The sample references
  `letsencrypt-production-default`.
- Internal DNS pointing the selected hostname to the existing Traefik address.

No additional MetalLB address is required. Machine clients authenticate directly
at vmauth and must not be redirected through an interactive login flow.

## Deployment

Run these steps from `Applications/MonitoringLogs`.

### 1. Create an Environment Overlay

```sh
cp -r overlay/_SAMPLE overlay/my-environment
umask 077
chmod 600 overlay/my-environment/secrets/secret-monitoring-logs-auth.env
```

Use an overlay name that does not begin with an underscore. Ordinary overlays
and `.env` files are ignored by this repository. Ignore rules are not encryption.
Never force-add credentials or rendered Secret manifests.

The sample is structurally complete but intentionally not deployable as a secure
environment. Its hostname, organization and credentials are public examples.

### 2. Configure Credentials and Users

Replace every value in
`overlay/my-environment/secrets/secret-monitoring-logs-auth.env` with an
independent credential. Prefer at least 32 random bytes encoded as hex.

```dotenv
WRITER_CLUSTER_A_TOKEN=<unique-random-writer-token>
GRAFANA_USERNAME=grafana-reader
GRAFANA_PASSWORD=<unique-random-reader-password>
TELEMETRY_TOKEN=<unique-random-telemetry-token>
```

Edit `configs/auth.yml` at the same time. Add or remove writer users and Secret
keys together. There is no fixed cluster count. Each cluster receives only its
own writer token. Keep reader and telemetry credentials separate from all writer
tokens. Do not remove `Authorization:` or `X-Scope-OrgID:` from the forwarded
header removal list.

Writers may only use `POST /loki/api/v1/push`. The Grafana reader may only use
allowlisted read endpoints through `GET`. The telemetry credential may only read
the Loki and vmauth metrics endpoints. vmauth does not enforce HTTP methods, so
Traefik's method-specific routes and the NetworkPolicies are part of this security
boundary. Loki itself stays reachable only from vmauth. The monitoring collector
uses the dedicated authenticated telemetry routes through Traefik.

### 3. Configure the Overlay

| File | Configuration |
| --- | --- |
| `configs/loki.yaml` | Retention, storage and conservative query settings |
| `patches/certificate.yaml` | Certificate DNS name and organization |
| `patches/ingressroute-write.yaml` | The same hostname for authenticated writes |
| `patches/ingressroute-query.yaml` | The same hostname for queries and telemetry |
| `patches/pvc.yaml` | Initial PVC capacity |
| `patches/resource-quota.yaml` | Namespace quota with rollout headroom |
| `transformers/images.yaml` | Pinned Loki and vmauth versions |
| `transformers/labels.yaml` | Deployment labels |
| `transformers/replicas.yaml` | Keep Loki at exactly one replica |

Replace `logs.example.com` consistently in the Certificate and both
IngressRoutes. Keep all existing path and method restrictions.

The sample uses 90 days (`2160h`) of retention and rejects initial ingestion more
than seven days old. The latter bounds accidental historical replay and does not
shorten stored retention. Do not change the schema start date after data exists.
Do not scale this filesystem-backed StatefulSet above one replica.

### 4. Review Storage Policy

Before deployment, inspect the effective Longhorn StorageClass and recurring-job
groups. The existing Longhorn offsite-backup mechanism may protect the Loki
volume. Confirm its effective job assignment, access protection and bounded
retention. Local and remote snapshots/backups can keep logs after Loki has
expired them, so their lifecycle is independent from Loki's 90-day retention.

The PVC is retained if the StatefulSet is scaled down or deleted. Deleting the
StatefulSet does not delete the claim. Never delete the PVC as a rollback step.

### 5. Validate and Deploy

Confirm the target context before applying anything:

```sh
kubectl config current-context
set -o pipefail
kustomize build overlay/my-environment > /dev/null
kustomize build overlay/my-environment | kubectl apply -f -
```

Rendered private overlays contain credentials, even when base64 encoded. Do not
print them into command logs or store them in shared temporary files.

Check the rollout without displaying Secret contents:

```sh
kubectl -n monitoring-logs rollout status statefulset/loki
kubectl -n monitoring-logs rollout status deployment/vmauth
kubectl -n monitoring-logs get pods,pvc
kubectl -n monitoring-logs wait --for=condition=Ready certificate/monitoring-logs --timeout=180s
```

### 6. Verify Access Boundaries

Use synthetic log lines without private data. Verify all of these cases through
the HTTPS hostname:

- A valid writer can push and cannot query.
- The Grafana reader can query and cannot push.
- Missing and incorrect credentials are denied.
- A client-provided `X-Scope-OrgID` does not reach Loki.
- Wrong methods and unlisted paths do not route.
- Loki cannot be reached directly from ordinary application Pods.
- `/loki/api/v1/tail`, delete, ruler and administrative APIs are not exposed.

Live tail is intentionally unavailable until its authenticated WebSocket route
has been tested separately. Do not expose it just to satisfy a Grafana feature
check.

## Network Requirements

| Source | Destination | Protocol / destination port | Purpose |
| --- | --- | --- | --- |
| Log agents and Grafana | Traefik HTTPS endpoint | TCP 443 | Writes and queries |
| Traefik Pods | vmauth | TCP 8427 | Authenticated proxy |
| vmauth | Loki | TCP 3100 | Authorized writes and queries |
| Monitoring collector | Traefik HTTPS endpoint | TCP 443 | Authenticated backend telemetry |
| Kubelet | Loki / vmauth Pods | TCP 3100 / 8426 | Health probes |
| Backend Pods | Cluster DNS | UDP/TCP 53 | Name resolution |
| cert-manager | Issuer and DNS-provider APIs | Usually TCP 443 | Certificate lifecycle |

Traefik's Service may translate external port 443 to another container port.
Client egress policies must account for the actual CNI and NAT behavior. Ports
3100, 8426 and 8427 must not be exposed externally. No new host firewall port is
required by this backend.

## Storage and Resources

| Component | CPU request / limit | Memory request / limit |
| --- | --- | --- |
| Loki | 0 / 1 CPU | 0 / 2Gi |
| vmauth | 0 / 200m | 0 / 128Mi |

CPU and memory requests are explicitly zero so Kubernetes does not default them
to the limits. This permits overcommit and increases eviction risk under node
pressure. The values are conservative starting ceilings for a small homelab, not
capacity guarantees. Measure ingestion rate, query load, throttling, memory and
restarts after deployment.

Fifty GiB is an initial capacity, not a promise that 90 days will fit. Measure
daily growth for at least several days and include WAL, index, cache and free
space in projections. Loki removes expired data through the compactor. It does
not evict data when the disk fills. Expand the PVC before capacity becomes tight.
Persistent volumes cannot be shrunk.

Changing a StatefulSet claim template does not resize an existing claim. Expand
the actual PVC and update the overlay together. Kubernetes may require controlled
StatefulSet recreation while retaining the claim.

## Credential Rotation and Rollback

Rotate a server credential and its client configuration as one coordinated
change. A direct replacement has no overlap window and can briefly interrupt
writes or queries. Verify the corresponding operation after rotation.

For an application rollback, restore the previous pinned image tags and config,
render, review and apply the overlay again. Schema and storage migrations require
release-specific review. Do not roll back across incompatible Loki schema or WAL
changes, and never remove the PVC to repair configuration or authentication.

## Troubleshooting

- **PVC pending:** Check StorageClass, Longhorn capacity and PVC events.
- **Loki fails to start:** Validate `loki.yaml`, volume ownership and writable
  `/var/loki` paths.
- **vmauth fails to start:** Check that every referenced placeholder has a
  matching Secret key. Do not print the Secret.
- **HTTP 401/403:** Check credentials and the source IP seen by Traefik.
- **HTTP 404:** Check hostname, method and allowlisted path.
- **HTTP 502/503:** Check readiness, Service endpoints, NetworkPolicies and disk.
- **Retention does not remove data:** Check compactor logs and retention metrics.
- **Certificate pending:** Check issuer, DNS and challenge status. Keep TLS
  verification enabled.

Inspect logs locally and redact credentials, hostnames and log payloads before
sharing them.

## Application Log Coverage

MonitoringAgent collects container stdout/stderr through Kubernetes CRI logs.
Applications that write exclusively to private files require explicit additional
configuration. The collector does not traverse application PVCs.

- Home Assistant's ordinary local log files need no separate collection when
  the same output is available in container logs. Keep them locally if required
  for its UI. Fault dumps are not collected through the ordinary file source.
- The Home Assistant code-server editor also stores extension, session and
  protocol diagnostics on its PVC. These are intentionally local and can be
  inspected for a specific incident.
- Scrypted container output is collected. LevelDB `*.log` files are database
  journals and must not be ingested as application logs. Check newly added
  plugins for any separate logging behavior.
- PostgreSQL uses structured CNPG output with the collector's SQL/payload
  exclusions. Database logs are not a replacement for application audit records.

Use Log Explorer for source and time-range checks, and Log Pipeline Health to
distinguish intentional exclusions from delivery failures. Local diagnostics and
backups have their own retention, independent of Loki's retention period.
