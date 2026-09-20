# UniFi Monitoring

UnPoller v5.2.7 and a dedicated Grafana Alloy v1.19.2 instance collect UniFi
Network, Protect and UNAS telemetry on ADMIN01. Metrics are written to the
existing VictoriaMetrics path. UDM and UNAS SIEM records, plus supported API
events, are written to the existing Loki path.

The public `_SAMPLE` overlay is safe to render. It uses the RFC 5737
documentation-only range `192.0.2.0/24`, the generic Kubernetes DNS suffix
`cluster.local` and placeholder credentials. Real addresses, the actual cluster
DNS suffix, CA material and secrets belong in a Git-ignored environment overlay.

## Data coverage

| Product or source | Collected | Destination | Notes |
| --- | --- | --- | --- |
| Network API | Inventory, health, clients, ports, PoE, WAN, traffic, DPI, rogue APs, alarms and anomalies | VictoriaMetrics and Loki | Exact fields depend on controller and firmware |
| Protect API | Device state and supported event metadata | VictoriaMetrics and Loki | Thumbnails, snapshots, video and audio payloads are disabled |
| UNAS API | Console, network I/O, pools, RAID, disks and shares | VictoriaMetrics | UnPoller v5.2.7 does not export UNAS API events |
| UDM SIEM | Available security and system records, including IDS detail where emitted | Loki | Direct Syslog to the Alloy LoadBalancer |
| UNAS SIEM | Available storage and system records | Loki | Does not imply complete Drive file auditing |

Talk, Netconsole, IPFIX/NetFlow and packet capture are intentionally excluded.
No image endpoint is configured. `protect_thumbnails=false` is enforced in the
configuration and regression tests.

## Components

- `unpoller`, one Deployment, polls UDM and UNAS and exposes port 9130.
- `alloy-unpoller`, one StatefulSet with a 5 GiB retained WAL volume, scrapes
  UnPoller and receives API events and Syslog.
- `alloy-unpoller-syslog`, a LoadBalancer exposing UDP and TCP 1514. The private
  ADMIN01 overlay must pin it to `10.0.1.20`.
- Dedicated Metrics and Logs writer identities, both named
  `unpoller-writer` in their separate authentication domains.
- The existing ADMIN01 Metrics Alloy scrapes only `alloy-unpoller` telemetry. It
  does not scrape UnPoller a second time.

## Create the ADMIN01 overlay

Run from `Applications/Unpoller`:

```sh
umask 077
cp -r overlay/_SAMPLE overlay/admin01
chmod 600 overlay/admin01/secrets/*.env
```

Replace the documentation values in these files:

| File | Required values |
| --- | --- |
| `configs/up.conf` | UDM and UNAS HTTPS addresses, local read-only account names and CA settings |
| `configs/alloy.env` | Actual UDM and UNAS source IPs |
| `secrets/secret-unpoller-credentials.env` | Network password, Protect API key and UNAS password |
| `secrets/secret-alloy-unpoller-writers.env` | Dedicated Metrics and Logs writer tokens |
| `patches/network-policy-unpoller.yaml` | Exact UDM and UNAS `/32` destinations |
| `patches/network-policy-alloy.yaml` | Exact backend Service IPs |
| `patches/syslog-service.yaml` | `10.0.1.20` and the exact UDM and UNAS source `/32` ranges |

Network and Protect read credentials are mounted as read-only files. UnPoller
v5.2.7 does not resolve a `file://` password for the UNAS input, so the
Deployment injects `unas_password` from the same Kubernetes Secret as
`UP_UNAS_DEFAULT_PASS`. The value stays out of the ConfigMap and command line.

Set `spec.loadBalancerIP` to `10.0.1.20` and retain the
`metallb.io/address-pool: default-pool` annotation. MetalLB 0.16 rejects a
Service that combines `spec.loadBalancerIP` with `metallb.io/loadBalancerIPs`.
Before deployment, verify that `.20` is still absent from Kubernetes Services
and from external DHCP or static IP assignments.

The sample enables both UDP and TCP because the UniFi UI exposes only address
and port. After observing real traffic, remove the unused protocol from the
private Service and Alloy listener. Syslog has no login. Security therefore
depends on exact source IP ranges, NetworkPolicy, node or VLAN firewall rules,
and no internet route. Source IP filtering is not cryptographic authentication.

On the current UniFi interface, configure each capable console under
**Integration > System Logging / SIEM**. Select **SIEM Server**, enable the
required categories, then enter `syslog-unifi.logs.home.essing.org` and port
`1514`. The DNS record must resolve to the fixed LoadBalancer address
`10.0.1.20` from both appliances. Start with Security and System, then add
Monitoring, Internet and Power so volume and overlap can be measured. The
vendor documents this export as CEF. UI names can move between UniFi OS
releases, so record the actual UDM and UNAS versions during rollout. Do not
enable Netconsole. Do not enable **Remote Device Logging** merely for this
deployment. That support-log path is separate from the structured SIEM export.
See [UniFi System Logs and SIEM Integration](https://help.ui.com/hc/en-us/articles/33349041044119-UniFi-System-Logs-SIEM-Integration).

### Certificates

The public sample enables API certificate verification. The private ADMIN01
overlay explicitly disables it for UDM and UNAS because the appliances use
self-signed certificates that can rotate during updates. Connections remain
HTTPS, but UnPoller does not authenticate the peer certificate. Compensating
controls are the exact `/32` egress destinations and the restricted internal
network path.

### Writer tokens

Create separate random tokens in the ignored MonitoringMetrics and
MonitoringLogs overlays. Put the matching values in this application's private
writer Secret. Metrics-vmauth forces `cluster=ADMIN01`. Logs receive the same
cluster label in Alloy. Reader credentials and existing agent tokens must not be
reused.

## Validate without a cluster

```sh
kustomize build overlay/admin01 > /tmp/unpoller-admin01.yaml
kubectl create --dry-run=client -f /tmp/unpoller-admin01.yaml -o name
python3 -m unittest discover -s ../../tests/monitoring -v
```

Review the rendered output locally. It contains Secrets. Do not commit or share
it. Confirm that no documentation address or placeholder remains.

## Controlled rollout

No deployment is performed by repository tests. After explicit rollout
approval:

1. Recheck the Kubernetes context, MetalLB pool and ownership of `10.0.1.20`.
2. Deploy the two backend authentication changes first and verify both internal
   vmauth endpoints with the dedicated tokens.
3. Deploy this overlay and wait for the UnPoller Deployment and Alloy
   StatefulSet to become ready.
4. Send one harmless test record from each appliance. Confirm `appliance=udm`
   and `appliance=unas`, retained source IP, timestamp and complete CEF payload.
5. Enable SIEM categories in stages. Keep Network SIEM and API events separated
   by `source` while comparing overlap.
6. Verify Network, Protect and UNAS metrics in VictoriaMetrics, then check the
   four dashboards in Grafana's **Monitoring UniFi** folder.
7. Measure series count, Loki ingest volume, Alloy WAL occupancy, drops and API
   refresh failures before final resource sizing.

Useful checks:

```promql
up{cluster="ADMIN01",job=~"unpoller|alloy-unpoller"}
unpoller_controller_up{cluster="ADMIN01"}
unpoller_prometheus_cache_age_seconds{cluster="ADMIN01"}
```

```logql
{cluster="ADMIN01",source="unifi-siem"}
{cluster="ADMIN01",source="unpoller-api"}
```

## Rollback and incident handling

- Stop new SIEM traffic on UDM and UNAS first if ingestion is unsafe or noisy.
- Scale `alloy-unpoller` and UnPoller to zero only when collection must stop.
- Revert backend writer entries after producers are stopped. Revoking a token
  while Alloy still has WAL data causes retries.
- Keep the retained Alloy PVC during ordinary rollback. Delete it only after an
  explicit decision to discard buffered data.
- API or appliance unreachability must not cause a liveness restart loop. Check
  controller status and refresh-failure metrics instead.
- UDP records can be lost before Alloy accepts them. The WAL protects accepted
  writes, not packets lost in transit.

Netconsole is not required and must remain disabled. IPFIX is flow telemetry,
not a replacement for SIEM or UnPoller metrics, and is outside this deployment.
