# UniFi Monitoring: Architektur und Implementierungsplan

Stand: 20.09.2026. Status: Repository-Implementierung auf `codex/unifi-monitoring`, noch nicht deployed.

Dieser Plan ist die verbindliche Grundlage für die Umsetzung durch Sol. Bestehende
Repository-Konventionen gelten ergänzend. Die Architekturentscheidungen sind mit
dem Nutzer abgestimmt. Routineentscheidungen innerhalb dieses Umfangs benötigen
keine erneute Architekturfreigabe.

## 1. Ziel und festgelegter Umfang

Auf ADMIN01 werden UnPoller und eine dedizierte Alloy-Instanz `alloy-unpoller`
betrieben. Sie ergänzen die vorhandenen VictoriaMetrics-, Loki- und
Grafana-Installationen.

| Festlegung | Vorgabe |
| --- | --- |
| Deployment-Ziel | Ausschließlich K3s-Cluster ADMIN01 |
| Anwendungen | UniFi Network, Protect und UNAS / Drive |
| Geräte | UDM, Switches, Access Points, LTE-Anbindung, Kameras und UNAS, soweit vom Collector unterstützt |
| Metriken | Alle für diesen Umfang verfügbaren sinnvollen Geräte-, Port-, WAN-, WLAN-, Client-, DPI-, Rogue-AP-, Protect- und UNAS-Metriken |
| Ereignisse | SIEM-Syslog von UDM und UNAS sowie ergänzende API-Ereignisse einschließlich IDS-Details und Protect |
| Bilder | Keine Thumbnails, Snapshots, Base64-Bilder, Video- oder Audioinhalte |
| Nicht enthalten | Talk, Netconsole, IPFIX/NetFlow-Collector, Paketmitschnitte |
| Syslog-Adresse | Fest `10.0.1.20` aus dem ADMIN01-MetalLB-Pool, kein DHCP |
| Externe Kommunikationspartner | UDM und UNAS. Protect wird auf der UDM angenommen und muss dort verifiziert werden |
| Interner Datenverkehr | Kubernetes-Services, kein Umweg über externe Ingress-Adressen |
| Aufbewahrung | Bestehende Backend-Retention übernehmen, derzeit als 90 Tage dokumentiert |

"Alle Daten" bedeutet alle tatsächlich verfügbaren textbasierten Daten des
vereinbarten Umfangs. Es bedeutet keine garantierte Erfassung jeder Verbindung,
kein vollständiges Drive-Audit ohne passende Quelle und keine Paketaufzeichnung.
DPI und Rogue-AP-Erfassung liefern überwiegend Metriken für VictoriaMetrics.
IDS und Systemereignisse liefern Logs für Loki.

Clientnamen, MACs, IPs, SSIDs, Anwendungen und IDS-Details dürfen für die Diagnose
erhalten bleiben. Keine pauschale Anonymisierung oder Entfernung dieser Daten.
Zugangsdaten und Tokens müssen weiterhin geschützt und aus Logausgaben redigiert
werden. Hohe Kardinalität wird gemessen und dokumentiert, nicht durch heimliches
Abschalten angeforderter Funktionen gelöst.

## 2. Architektur

```text
UDM (Network + Protect) -- HTTPS API --\
                                        UnPoller
UNAS ------------------- HTTPS API --/      |
                                           | /metrics + ergänzende Loki-Push-Events
                                           v
UDM  -- SIEM/Syslog --> 10.0.1.20 --> alloy-unpoller
UNAS -- SIEM/Syslog --> 10.0.1.20 -->     |
                                         +-- Remote Write --> Metrics-vmauth --> VictoriaMetrics
                                         +-- Loki Push -----> Logs-vmauth ----> Loki

Bestehendes Grafana --> bestehende Datasources / Backends
Bestehender alloy-metrics --> Eigenmetriken von alloy-unpoller
Bestehender alloy-logs --> stdout/stderr von UnPoller und alloy-unpoller
```

Alle Pfeile außer den Verbindungen zu UDM und UNAS bleiben clusterintern.

### Verantwortlichkeiten

- `alloy-metrics`: bestehende Kubernetes-, Host- und Anwendungsmesswerte.
- `alloy-logs`: bestehende Pod-, Journal- und Hostlogs.
- `alloy-unpoller`: ausschließlich UnPoller-Scraping, UniFi-Syslog und ergänzende
  UnPoller-Ereignisse, inklusive Verarbeitung, Pufferung und Weiterleitung.
- UnPoller: lokale API-Abfragen, Prometheus-Endpoint und unterstützte Ereignisexporte.

`alloy-unpoller` ist eine eigene Instanz, kein zusätzlicher Konfigurationsblock im
bestehenden Metrics-Alloy. Sie erhält keinen Kubernetes-API-Zugriff. Statische
Service-Ziele reichen für die Sammlung aus. Ihr ServiceAccount-Token wird nicht
automatisch eingebunden. Der bestehende Metrics-Alloy überwacht ihre Eigenmetriken,
scrapt aber nicht zusätzlich den UnPoller-Endpoint.

### Workloads und Speicherung

- UnPoller: Deployment mit einer Replica und `Recreate`, zunächst ohne PVC.
- `alloy-unpoller`: StatefulSet mit einer Replica und einem PVC für die getrennten
  Remote-Write- und Loki-WAL-Verzeichnisse. Retain-Verhalten wie bei bestehenden
  Monitoring-Workloads. Keine parallelen aktiven Collector-Replicas.
- Ausgangswerte: UnPoller 100m CPU / 128Mi Request, 500m / 512Mi Limit.
- Ausgangswerte: Alloy 100m CPU / 256Mi Request, 1000m / 1Gi Limit, 5Gi PVC.
- Diese Werte sind vorläufige Budgets. Mit aktivem DPI, Rogue und IDS messen und
  bei Bedarf begründet anpassen. Backend-Speicherbedarf separat erfassen.
- Startup und Readiness prüfen den Prozess. Fehlende UniFi-Erreichbarkeit darf
  keine Liveness-Neustartschleife erzeugen.
- WAL puffert bereits angenommene Daten. Kein Versprechen verlustfreier UDP-
  Übertragung oder vollständiger API-Nachholung nach einem Ausfall.

## 3. Netzwerk und Schutz

### Syslog-Eingang

Ein dedizierter LoadBalancer-Service zeigt nur auf den Syslog-Port von
`alloy-unpoller`. Geplanter äußerer und innerer Port ist 1514, damit der Container
ohne privilegierten Port läuft. Falls die Sender einen anderen Port benötigen,
kann der Service diesen auf 1514 abbilden.

Im privaten ADMIN01-Overlay:

```yaml
metadata:
  annotations:
    metallb.io/address-pool: default-pool
    metallb.io/loadBalancerIPs: 10.0.1.20
spec:
  type: LoadBalancer
  externalTrafficPolicy: Local
```

Am 20.09.2026 read-only live geprüft: `default-pool` enthält
`10.0.1.1-10.0.1.128`, `autoAssign: false`. Services belegten `.1`, `.11`, `.12`
und `.13`. `.20` war keinem Service zugewiesen. Vor Deployment erneut prüfen,
einschließlich externer IPAM-/DHCP- und statischer Belegung. Ein fehlgeschlagener
Ping allein beweist nicht, dass eine Adresse frei ist.

Öffentliche `_SAMPLE`-Dateien verwenden Dokumentationsadressen, keine echten
Managementadressen oder Credentials. Die konkrete `.20` gehört in das private
ADMIN01-Overlay. MetalLB benötigt keine DHCP-Reservierung, die Adresse darf aber
nicht gleichzeitig anderweitig vergeben werden.

- Zuerst eine Testnachricht von UDM und UNAS untersuchen: tatsächliche Quell-IP,
  UDP oder TCP, Syslog-Rahmen, CEF-Inhalt, Zeitstempel, maximale Nachrichtengröße.
- Nur die tatsächlich benötigten Protokolle veröffentlichen. Nicht aus den
  Eingabefeldern "IP und Port" auf TCP-, TLS- oder UDP-Unterstützung schließen.
- Beide tatsächlichen Senderadressen als einzelne `/32` freigeben. Keine
  pauschale Freigabe eines gesamten privaten Netzes.
- Default-Deny-NetworkPolicies, passende Ingress-/Egress-Regeln und dokumentierte
  Node-/Netzwerk-Firewallregeln. `loadBalancerSourceRanges` ergänzend verwenden,
  dessen tatsächliche Durchsetzung im vorhandenen K3s-Datenpfad testen.
- Quell-IP-Erhaltung durch `externalTrafficPolicy: Local` live nachweisen.
- NodePort-Zugriffe außerhalb dieser Regeln ausschließen. Nicht blind
  `allocateLoadBalancerNodePorts: false` setzen, zuerst Datenpfad-Kompatibilität prüfen.
- Zugriff von einer unerlaubten Quelle auch im gleichen VLAN testen. Dieser
  Verkehr passiert möglicherweise keine Router-Firewall.
- Keine Internetfreigabe. Kein Login wird von den Syslog-Sendern erwartet.
- IP-Freigaben sind keine kryptografische Absenderauthentifizierung. Bei UDP
  verbleiben Spoofing- und Verlustgrenzen, auch wenn nachgelagert eine WAL existiert.
- Obergrenzen für Nachrichtengröße, Warteschlangen und Ressourcen konfigurieren.
  Drops und Parserfehler sichtbar machen, keine stillen Inhaltsabschneidungen.

### Clusterinterne Wege

- Eigene ClusterIP-Services für UnPoller `/metrics`, Alloy-Eigenmetriken und
  den ausschließlich intern erreichbaren Loki-Push-Eingang.
- Metrics-Ausgang auf ADMIN01 über `vmauth.monitoring-metrics.svc.admin01.home.essing.org:8427/api/v1/write`.
- Logs-Ausgang auf ADMIN01 über `vmauth.monitoring-logs.svc.admin01.home.essing.org:8427/loki/api/v1/push`.
- Bestehende vmauth-Authentifizierung beibehalten, keine direkten Schreibzugriffe
  auf die ungeschützten Datenbank-Endpunkte.
- Für diesen Baustein eigene Writer-Tokens pro Backend verwenden, getrennt von
  Reader- und bestehenden Agent-Credentials. Metrics-vmauth erzwingt
  `cluster=ADMIN01`, Loki erhält dieses Label im Collector.
- Der bestehende interne vmauth-Port verwendet HTTP. Planungsentscheidung:
  HTTP nur innerhalb des Clusters, geschützt durch enge NetworkPolicies.
  Das ist keine Transportverschlüsselung. Externe API-Verbindungen bleiben HTTPS
  mit Zertifikatsprüfung. Keine implizite Erweiterung um einen neuen TLS-Proxy.
- Bestehende Agent-Ausgänge anderer Pipelines und Cluster nicht nebenbei ändern.
- UnPoller-Egress nur DNS, UDM/UNAS TCP 443 und interner Ereigniseingang.
- Alloy-Egress nur DNS, UnPoller und die beiden vmauth-Services.
- Benötigte Ziel-Ingress-Regeln in den Backend-Namespaces explizit ergänzen.
- Kein `hostNetwork`, kein `hostPort`, keine unnötigen Linux-Capabilities.

## 4. Datenvertrag

### API-Zugänge und Funktionsprüfung

UnPoller v5.2.7 und Alloy v1.19.2 sind die geprüften Ausgangskandidaten, keine
Aufforderung, ein bewegliches `latest` zu verwenden. Vor Implementierung die
benötigten Optionen am konkreten Tag und Containerimage bestätigen, anschließend
Versionen und gegebenenfalls Digests pinnen.

- Network: dedizierter lokaler Zugang mit den minimal erforderlichen Leserechten.
  API-Key oder lokales Konto nach nachgewiesener Abdeckung der benötigten Endpoints.
- Protect: eigener Integration-Key. Hosting auf der UDM und API-Rechte verifizieren.
- UNAS: eigener Zugang am UNAS und eigener UNAS-Input. Nicht als Network-Controller
  konfigurieren. Modell und UniFi-OS-/Drive-Version konkret prüfen.
- Höhere Rechte nur bei belegter Notwendigkeit dokumentieren, nicht vorsorglich
  einen allgemeinen Superadmin verwenden.
- Zertifikatsprüfung einschalten, passende CA-Dateien bereitstellen.
- SecretGenerator, read-only Secret-Mounts und unterstützte dateibasierte
  Credentials verwenden. Keine gerenderten privaten Secrets ausgeben oder committen.

### Metriken

- Network, Protect-Geräte und UNAS aktivieren.
- DPI und Rogue-AP-Erfassung aktivieren. Die tatsächlichen Optionsnamen sowie
  API-/Firmware-Einschränkungen an der gepinnten Version prüfen.
- Start: 60s API-Cache-Aktualisierung und 60s Scrape. Request- und Scrape-Timeouts
  zueinander passend einstellen, Retry-/429-Verhalten testen.
- `job="unpoller"`, serverseitiges `cluster="ADMIN01"`, stabile Source-/Site-/
  Device-Labels. Keine Abhängigkeit der Geräteidentität von wechselnden Podnamen.
- Unterschiedliche Metrikpräfixe der Network-, Protect- und UNAS-Collector beachten.
- Client- und DPI-Serien nicht unbemerkt durch allgemeine Filter entfernen.
- Keine generische Scrape-Opt-in-Markierung am UnPoller-Pod, wenn dadurch der
  bestehende `alloy-metrics` dieselben Daten zusätzlich abholt.
- LTE-WAN-Sicht und verfügbare Modemwerte anhand echter Ausgabe dokumentieren.
  Keine Signalqualitätsmetriken erfinden, wenn das Modell sie nicht exportiert.

### Logs

- UDM und UNAS sollen beide ihre verfügbaren SIEM-Kategorien per Syslog senden.
- Der Umfang des UNAS-Exports ist vor Ort zu prüfen. SIEM-Syslog nicht automatisch
  mit vollständiger Datei-/Benutzer-Auditierung von Drive gleichsetzen.
- Network-Systemereignisse bevorzugt aus SIEM. UnPoller ergänzt fehlende
  IDS-/Alarm-/Anomalie-/Protect-Kategorien über seinen Loki-Ausgang.
- Für jede Kategorie eine Tabelle führen: Quelle, aktiviert, Beispiel erhalten,
  enthaltene Felder, Überschneidung, bekannte Lücke. Erst nach dem Vergleich einen
  redundanten API-Kanal deaktivieren. Keine angeforderte Kategorie zur Vermeidung
  von Duplikaten ersatzlos streichen.
- Im Probebetrieb dürfen parallele Quellen mit getrennten `source`-Labels laufen.
  Vor Abnahme Zuständigkeit pro Kategorie festlegen. Keine garantierte globale
  Exactly-once-Verarbeitung behaupten.
- Protect-Logs aktivieren, `protect_thumbnails=false`. Medienfelder auch mit
  Testfixtures ausschließen. Keine Snapshot-/Stream-Endpunkte abrufen.
- Betriebslogs von UnPoller und Alloy weiterhin durch vorhandenen Log-DaemonSet
  sammeln. Nicht zusätzlich über den Ereignispfad duplizieren.
- Startintervall für API-Ereignisse: 60s gemäß der 15/30/60-Konvention. Syslog ist ereignisgetrieben.
- Labels klein halten: `cluster`, `service_name`, `source`, Anwendung und wenige
  stabile Site-/Schweregrad-/Kategorie-Dimensionen. MACs, Client-IPs, SSIDs,
  Benutzernamen, Event-IDs und Freitext bleiben im Inhalt oder in Metadaten.
- Tatsächliche Transportquelle getrennt vom behaupteten CEF-Host erfassen.
- Vollständigen textbasierten Ereignisinhalt nach Credential-Redaktion erhalten.
  Parserfehler nicht verwerfen, sondern markiert zur Diagnose weiterleiten.
- CEF-Escaping, Zeitzonen, fehlende Zeitstempel und mehrzeilige Inhalte testen.
  Eingangszeit als klar dokumentierter Fallback. Alte Ereignisse nach bestehenden
  Loki-Annahmegrenzen behandeln und Drops zählen.
- Alloy unterstützt RFC3164/RFC5424. Für nicht standardkonformes CEF kann `raw`
  erforderlich sein. Das ist in der aktuellen Dokumentation experimentell und
  erfordert die passende Stability-Einstellung nur an `alloy-unpoller`. Erst anhand
  realer Nachrichten entscheiden. Keine Stability-Änderung bestehender Collector.
- Keine pauschale Inhalts-Sampling- oder Drop-Regel für DPI/IDS-bezogene Daten.

## 5. Repository-Umsetzung

Die folgenden Pfade sind geplante neue Dateien beziehungsweise Änderungsbereiche.
Feinere Dateinamen nach bestehenden Konventionen festlegen.

```text
Applications/Unpoller/
  README.md
  base/                         Namespace unpoller, Quota, Default-Deny und DNS
  components/_application/      UnPoller Deployment, Config, interne Services
  components/_alloy/            alloy-unpoller StatefulSet, WAL, Config, Services
  components/_syslog/           LoadBalancer und dazugehörige Policies
  overlay/_SAMPLE/              Öffentliche vollständige Vorlage
    configs/ generators/ patches/ secrets/ transformers/
  overlay/admin01/              Privat und Git-ignoriert

Applications/MonitoringAgent/   Ausschließlich Eigenüberwachung von alloy-unpoller
Applications/MonitoringMetrics/ Eigene UniFi-Writer-Identität und Ziel-Ingress
Applications/MonitoringLogs/    Eigene UniFi-Writer-Identität und Ziel-Ingress
Applications/MonitoringGrafana/ Generierte UniFi-Dashboards und Provisionierung
Applications/Grafana/           Erforderliche Mounts/Provisionierungsintegration
tests/monitoring/               Render-, Pipeline- und Dashboardtests
```

UnPoller und `alloy-unpoller` gehören zu einer gemeinsam deploybaren Anwendung im
Namespace `unpoller`, bleiben aber getrennte Workloads. `_SAMPLE` enthält keine
echten Adressen oder Zugangsdaten. Bestehende Generator-Hashes und Rollout-
Konventionen beibehalten. Private Overlays niemals force-adden.

Vier provisionierte Dashboards im neuen Ordner `Monitoring UniFi`:

1. Overview: Quellen, Collector-/API-Gesundheit, Aktualität, verfügbare Geräte,
   wichtige Ereignisse und Pipelinezustand.
2. Network: UDM, WAN/LTE, Switches/Ports/PoE, APs/WLAN, Clients, DPI, Nachbar-/
   Rogue-APs und IDS-/Systemereignisse.
3. Protect: verfügbare Recorder-/Kamera-Metriken und textbasierte Ereignisse.
4. UNAS: Gerät, Pools, Laufwerke, Shares und tatsächlich verfügbare SIEM-Ereignisse.

Vorhandene Datasource-UIDs `monitoring-metrics` und `monitoring-logs` nutzen.
Deterministische Python-Builder und vorhandene Gestaltungs-/Testkonventionen
wiederverwenden. Navigation aus Operations Center und zu Betriebslogs ergänzen.
Keine externen Grafana-Plugins oder zweite Grafana-Instanz.

HTTP-Scrape-Erfolg, erfolgreiche API-Abfrage und Datenaktualität sind getrennte
Signale. Gecachte Metriken dürfen bei ausgefallener API nicht als frischer Zustand
erscheinen. Geeignete reale Health-/Freshness-Metriken zuerst inventarisieren.
Fehlende Werte bleiben N/A. Rogue-AP-Erkennung allein ist kein Sicherheitsalarm.
Keine neuen Benachrichtigungskanäle oder vollständige Alerting-Plattform einführen.

## 6. Arbeitspakete und Reihenfolge für Sol

### A. Bestandsaufnahme und Kompatibilitätsnachweis

- Aktuelle Repository-Regeln und relevante Monitoring-Konfigurationen lesen.
- Sauberen Arbeitsstand prüfen, bestehende Änderungen erhalten. Für Implementierung
  Branch `codex/unifi-monitoring` verwenden, wenn noch kein geeigneter Arbeitsbranch besteht.
- Modelle, UniFi-OS-/App-Versionen, UDM-/UNAS-Adressen, lokale Zugänge, Zertifikate
  und SIEM-Möglichkeiten read-only erfassen, soweit verfügbar.
- Quellen-/Capability-Matrix und konkrete Testfixtures ohne echte Geheimnisse erstellen.
- Vor Deployment IP `.20` und Senderadressen erneut prüfen.
- Fehlende Credentials oder reale Syslog-Beispiele als konkrete Live-Prüfpunkte
  festhalten. Unabhängige Manifest-/Fixture-Arbeit trotzdem abschließen.

### B. Anwendung und Transport

- Kustomize-Anwendung, beide Workloads, SecurityContext, PVC, Ressourcen, Services
  und Policies implementieren.
- Statisches UnPoller-Scraping und beide getrennten internen Writer-Pfade umsetzen.
- Writer-Identitäten in öffentlichen Beispielen und privaten Overlays konsistent
  ergänzen, ohne bestehende Tokens zu ändern oder preiszugeben.
- Eigenmetriken von `alloy-unpoller` in das bestehende Monitoring aufnehmen.
- Konfiguration mit dem tatsächlich gepinnten Image validieren und ausführen.

### C. Quellen und Log-Verarbeitung

- Network, Protect, UNAS, DPI und Rogue-Metriken aktivieren und prüfen.
- Syslog für beide Konsolen sowie internen UnPoller-Loki-Push umsetzen.
- CEF-Verarbeitung, Quellzuordnung, Medienausschluss, Credential-Redaktion,
  Zeitstempel und WAL testen.
- Überschneidungen zwischen SIEM und API anhand der Capability-Matrix auflösen.

### D. Dashboards und Betriebsdokumentation

- Dashboards aus realen oder versionsgebunden belegten Metriken erstellen.
- Setup, Zugangsvoraussetzungen, konkrete UniFi-Menüs nach geprüfter Version,
  Firewallregeln, Secret-Rotation, Fehlerdiagnose und Rollback dokumentieren.
- Release-/Index-Dokumentation nur nach vorhandener Repository-Konvention ergänzen.
- Bekannte Grenzen zu LTE, UNAS-Audit, Event-Nachholung und UDP explizit benennen.

### E. Prüfung und Übergabe

- Zuerst fokussierte neue Tests, anschließend vorhandene Monitoring-Regression.
- Öffentliche Beispiele und verfügbare private Overlays rendern, private Ausgabe
  ausschließlich verwerfen oder geschützt verarbeiten, nie in geteilte Logs schreiben.
- Änderungen und nicht live verifizierte Punkte klar zusammenfassen.
- Deployment-/UniFi-Konfigurationsänderungen als ausführbares Runbook vorbereiten.
  Dieser Plan autorisiert die Implementierung, aber keinen automatischen Live-
  Rollout, Push oder das Ändern von Firewall-/UniFi-Produktionskonfiguration.
  Dafür vorhandene ausdrückliche Freigabe prüfen oder abschließend konkret anfordern.

## 7. Verifikation und Abnahmekriterien

### Automatisierbar vor Deployment

- Kustomize rendert die neue Anwendung und alle betroffenen Monitoring-/Grafana-
  Overlays ohne ungültige Referenzen. Genau eine aktive UniFi-Collector-Replica.
- Sample-Config enthält nur Platzhalter. Keine Secrets in ConfigMaps, generierten
  Dashboards oder Testausgaben. Rollout bei Config-/Secret-Änderung funktioniert.
- Alloy-Konfiguration läuft mit gepinntem Image und den erforderlichen Stability-
  Flags. UnPoller startet non-root mit schreibgeschütztem Root-Dateisystem.
- Mock-API-/versionsgebundene Fixtures für Network, Protect und UNAS, einschließlich
  Fehlern, Timeouts, 401/403 und 429. Keine Abhängigkeit von produktiven Credentials.
- Syslog-Fixtures für beide Senderformate: CEF-Escaping, große Nachrichten,
  Zeitstempel, fehlerhafte Inhalte, IDS-Details und eindeutige Quellenzuordnung.
- Loki-Push-Fixtures: Protect-Ereignisse ohne Medien, keine Bilddaten in Endausgabe,
  keine Credential-Leaks, keine hochvariablen Indexlabels.
- Remote-Write-/Loki-Testempfänger bestätigen korrekte Pfade, Authentifizierung,
  Labels und payloads. Fehlerantworten und verzögerte Backends prüfen.
- WAL-Wiederanlauf nach Pod-Ersatz mit erhaltenem Volume testen. Verluste/Duplikate
  an den Grenzen erfassen, nicht nur Konfigurationsstrings prüfen.
- Dashboard-Erzeugung deterministisch. Abfragen gegen lokale Testbackends mit
  Fixture-Daten prüfen. Fehlende Daten und ausgefallene API bleiben sichtbar.
- Bestehende Tests: `python3 -m unittest discover -s tests/monitoring -v`.
  Zusätzliche Runtime-/Privat-Overlay-Tests gemäß Repository-Voraussetzungen.

### Live nach gesondert freigegebenem Rollout

- MetalLB weist ausschließlich die angeforderte `10.0.1.20` zu, keine Kollision.
- Je eine echte SIEM-Testnachricht von UDM und UNAS in Loki nachweisbar.
- Tatsächliche Sender-IP bleibt erhalten. Unerlaubte Quelle wird blockiert,
  einschließlich gleicher VLAN- und NodePort-Zugriffspfade.
- Network, Protect und UNAS liefern belegte Metriken. DPI, Rogue und IDS bleiben
  aktiviert, tatsächliche Datenverfügbarkeit und Lücken werden dokumentiert.
- UniFi-Pipeline benutzt ClusterIP-Ziele und die eigenen Writer-Credentials.
- Keine doppelten UnPoller-Scrapes. Keine unbeabsichtigte doppelte Event-Kategorie.
- Collector-, API- und Freshness-Status stimmen mit kontrollierten Fehlerszenarien
  überein. Keine automatischen Neustartschleifen bei API-Ausfall.
- Mindestens 24 Stunden Beobachtung nach vereinbartem Betriebsfenster: CPU/RAM,
  aktive/neue Serien, Logvolumen, Drops, 429, WAL-Belegung und Backendwachstum.
  Nicht synchron darauf warten oder ungefragt eine Automation erstellen.
- Kein Bild-, Audio- oder Videoinhalt gespeichert. Talk und Netconsole deaktiviert.
- Bestehende Monitoring-Pipelines funktionieren weiterhin.

Implementierung und Live-Abnahme getrennt berichten. Ohne echte Sendernachrichten,
Zugänge oder Deployment-Freigabe keine vollständige Live-Verifikation behaupten.

## 8. Rollout und Rollback

Rollout-Reihenfolge: Backend-Writer und Ziel-Policies, Anwendung/PVC, interne
Metriken/API-Ereignisse, Syslog-Quellkonfiguration, Grafana, Live-Abnahme.

Rollback: SIEM-Versand an den neuen Eingang stoppen, UnPoller und `alloy-unpoller`
herunterfahren und neue Eigenüberwachung deaktivieren. PVC/WAL sowie gespeicherte
Backenddaten erhalten. Writer erst nach gestoppten Schreibern deaktivieren.
LoadBalancer-IP erst freigeben, wenn beide Sender nicht mehr dorthin senden.
Keine vorhandenen Agent-PVCs, Backenddaten oder anderen Writer verändern.

## 9. Referenzen

- Bestehende Architektur: `Applications/MonitoringAgent/README.md`,
  `Applications/MonitoringMetrics/README.md`, `Applications/MonitoringLogs/README.md`,
  `Applications/MonitoringGrafana/README.md`.
- [UnPoller v5.2.7](https://github.com/unpoller/unpoller/releases/tag/v5.2.7)
- [Versionsgebundene UnPoller-Konfiguration](https://github.com/unpoller/unpoller/blob/v5.2.7/examples/up.conf.example)
- [Alloy Syslog](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.syslog/)
- [Alloy Loki-Push-Eingang](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.api/)
- [UniFi SIEM](https://help.ui.com/hc/en-us/articles/33349041044119-UniFi-System-Logs-SIEM-Integration)
- [UniFi Traffic Logging / IPFIX](https://help.ui.com/hc/en-us/articles/32201256219799-Traffic-Flows-and-Traffic-Logging-in-UniFi-Network)
- [MetalLB Service-Konfiguration](https://metallb.io/usage/)
- [Kubernetes Quell-IP-Erhaltung](https://kubernetes.io/docs/tutorials/services/source-ip/)

Aktuelle Web-Dokumentation kann vom gepinnten Release abweichen. Die Implementierung
muss versionsgebundene Quellen und Runtime-Tests als maßgeblich behandeln.
