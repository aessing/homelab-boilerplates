# Vendor telemetry policy

Disable manufacturer usage statistics, anonymous telemetry and automatic error
reports through each application's supported settings. Preserve these controls
in shared resources, `_SAMPLE` overlays and private cluster overlays. Runtime-only
preferences must be checked separately when the application manages them itself.

Local Prometheus metrics, log collection and the Homelab's `/telemetry/` endpoints
are part of the monitoring system. They remain enabled. Required application
APIs, integrations and licensing are separate from anonymous usage reporting.

## Supported controls

| Component | Control | Scope |
| --- | --- | --- |
| Alloy | `--disable-reporting` | Metrics and log agents on all clusters, plus Alloy-Unpoller |
| Grafana | `GF_ANALYTICS_REPORTING_ENABLED=false` | Anonymous vendor reporting. Local metrics remain enabled. |
| Loki | `analytics.reporting_enabled: false` | Already present in the shared config and sample |
| Authentik | `authentik.error_reporting.enabled: false`, `send_pii: false`, `disable_startup_analytics: true` | Already present in the sample and effective deployment values |
| Traefik | `global.sendAnonymousUsage: false`, `global.checkNewVersion: false` | Its version checker also supplies data used for vendor statistics |
| Longhorn | `defaultSettings.allowCollectingLonghornUsageMetrics: false`, `defaultSettings.upgradeChecker: false` | Verify persistent `allow-collecting-longhorn-usage-metrics` and `upgrade-checker` settings as well as Helm defaults |
| Homepage | `NEXT_TELEMETRY_DISABLED=1` | Explicit opt-out in the Deployment, in addition to the official image's build setting |
| Home Assistant | All five Analytics preferences disabled | Runtime preference, managed through the supported `analytics` / `analytics/preferences` WebSocket commands. No container environment or YAML setting. |
| HA Code Server | `--disable-telemetry` | Already supplied by the official LinuxServer image's start script |

Home Assistant's `base`, `usage`, `statistics`, `diagnostics` and `snapshots`
preferences must all be false. Use the supported API or Settings UI, rather than
editing its live storage files. No device or integration changes are required.

Keep ordinary update checks that do not report usage separate from this policy.
Traefik and Longhorn are exceptions because their version checks send information
used by the vendor. Disabling those checks removes version notifications from
their UIs, it does not disable ingress, storage or local monitoring.

## Verification limits

The configuration and official-source review on 2026-10-04 found no additional
automatic manufacturer-reporting candidate in the supplied definitions for
Unpoller, VictoriaMetrics, Uptime Kuma, HomeCDN, Timeserver, PostgreSQL, MariaDB,
Mosquitto or the reviewed Kubernetes operators. Unpoller's `report_errors` is a
local Prometheus error-reporting option, not vendor telemetry.

Grafana Renderer's OpenTelemetry tracing requires a configured endpoint. No
external tracing endpoint is configured here. Scrypted's public core and plugins
did not expose a supported manufacturer-telemetry switch in this review.
Proprietary Scrypted NVR components and independently installed plugins or editor
extensions are not fully covered. Do not invent environment variables or block
functional cloud connections to claim coverage.

These are configuration and source checks, not a packet capture or a guarantee
that every optional plugin makes no external connection. Applications whose names
begin with NSE, including their associated app projects, are outside this audit
and deployment scope.

## Official references

- [Alloy anonymous usage reporting](https://grafana.com/docs/alloy/latest/data-collection/)
- [Grafana analytics settings](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#analytics)
- [Loki configuration](https://grafana.com/docs/loki/latest/configure/)
- [Authentik configuration](https://docs.goauthentik.io/install-config/configuration/)
- [Traefik data collection](https://doc.traefik.io/traefik/master/contributing/data-collection/)
- [Longhorn settings](https://longhorn.io/docs/1.13.0/references/settings/)
- [Home Assistant Analytics API](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/analytics/__init__.py)
- [LinuxServer Code Server startup](https://github.com/linuxserver/docker-code-server/blob/4.135.0-ls361/root/etc/s6-overlay/s6-rc.d/svc-code-server/run)
- [Homepage image build](https://github.com/gethomepage/homepage/blob/v2.4.0/Dockerfile)
