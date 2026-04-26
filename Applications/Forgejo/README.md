# Forgejo

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Forgejo](https://forgejo.org/), a self-hosted lightweight software forge, together with a [Forgejo Actions runner](https://forgejo.org/docs/latest/admin/actions/).

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Forgejo/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── namespace.yaml                              # Kubernetes namespace
│       ├── network-policy-clients-to-forgejo-ssh.yaml  # Allow SSH from RFC1918
│       ├── network-policy-runner-to-forgejo.yaml       # Allow runner -> forgejo HTTP
│       ├── network-policy-traefik-to-forgejo.yaml      # Allow traefik -> forgejo HTTP
│       └── resource-quota.yaml                         # Namespace resource quotas
├── components/
│   ├── _forgejo/                                       # Forgejo server (rootless)
│   │   └── resources/
│   │       ├── certificate.yaml                        # cert-manager certificate
│   │       ├── ingressroute.yaml                       # Traefik HTTPS route
│   │       ├── service.yaml                            # ClusterIP HTTP service
│   │       ├── service-ssh.yaml                        # LoadBalancer SSH service
│   │       └── statefulset.yaml                        # Forgejo StatefulSet
│   └── _runner/                                        # Forgejo Actions runner
│       └── resources/
│           ├── service.yaml                            # Headless service
│           └── statefulset.yaml                        # Runner + DinD sidecar
└── overlay/
    └── _SAMPLE/                                        # Template overlay
        ├── kustomization.yaml
        ├── configs/                                    # Runner config.yaml
        ├── generators/                                 # Secret/ConfigMap generators
        ├── patches/                                    # Environment-specific patches
        ├── secrets/                                    # Secret environment files
        └── transformers/                               # Image, label and replica transformers
```

## Features

- **Forgejo 15.0.0-rootless**: Runs as non-root (UID/GID 1000), no privilege escalation.
- **External PostgreSQL**: Uses an existing CloudNativePG / PostgreSQL cluster reached over SSL.
- **Persistent /data volume**: 32Gi `ReadWriteOnce` PVC on `longhorn-retain` for repositories, LFS, packages, indexers and logs.
- **Traefik IngressRoute**: HTTPS on `git.home.essing.org` via cert-manager-issued certificate.
- **SSH LoadBalancer**: Dedicated service for Git over SSH (port 22 → container 2222).
- **Forgejo Actions runner**: Bundled runner with Docker-in-Docker sidecar for CI/CD jobs.
- **Hardened defaults**: Per [Forgejo recommendations](https://forgejo.org/docs/latest/admin/setup/recommendations/) — registration disabled, sign-in required, password complexity enforced, twoqueue cache, committer trust model, only-relevant-repos UI.
- **SMTP-ready**: Mailer configured for SMTPS via env vars.

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- An existing PostgreSQL cluster reachable at `postgres-database-rw.postgres.svc.apps02.home.essing.org:5432`
  with a `forgejo` database and `forgejo` user, SSL enforced.
- [cert-manager](https://cert-manager.io/) with the `letsencrypt-production-default` ClusterIssuer
- [Traefik](https://traefik.io/) ingress controller exposing the `websecure` entry point
- [Longhorn](https://longhorn.io/) with the `longhorn-retain` storage class
- [MetalLB](https://metallb.universe.tf/) for the LoadBalancer SSH service
- [reloader](https://github.com/stakater/Reloader) for automatic restarts on secret changes

## Deployment

### 1. Create the database

On the PostgreSQL cluster, create the database and user:

```sql
CREATE USER forgejo WITH ENCRYPTED PASSWORD '<your-secure-password>';
CREATE DATABASE forgejo OWNER forgejo;
```

### 2. Create your overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/apps02
```

### 3. Configure secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-forgejo-database-user.env`** — Database credentials:

```dotenv
username=forgejo
password=<your-secure-password>
```

**`secrets/secret-forgejo-config.env`** — Forgejo `app.ini` overrides via `FORGEJO__*` env vars.
Replace at minimum:

| Placeholder | Purpose |
|-------------|---------|
| `###PLACEHOLDER_SMTP_USER###` | SMTP authentication username (mailer FROM address) |
| `###PLACEHOLDER_SMTP_PASSWORD###` | SMTP authentication password |

**`secrets/secret-forgejo-runner-token.env`** — Runner registration token:

```dotenv
token=<token-from-forgejo-admin-ui>
```

The token is generated in Forgejo at `Site Administration → Actions → Runners → Create new runner`
or via `forgejo forgejo-cli actions generate-runner-token`.

### 4. Configure patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate-forgejo.yaml` | TLS certificate organization + DNS names |
| `ingressroute-forgejo.yaml` | External hostname for Forgejo (e.g. `git.home.essing.org`) |
| `pvc-forgejo.yaml` | Forgejo data volume size (default: 32Gi) |
| `pvc-forgejo-runner.yaml` | Runner data volume size (default: 10Gi) |
| `resource-quota.yaml` | Namespace pod and PVC limits |
| `service-forgejo-ssh.yaml` | MetalLB IP for the SSH LoadBalancer |

### 5. Configure the runner

The runner uses `code.forgejo.org/forgejo/runner` with a Docker-in-Docker sidecar (DOCKER_HOST=tcp://localhost:2376).
Adjust labels/capacity in `configs/forgejo-runner.yaml` if needed.

### 6. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/apps02

# Apply to the cluster
kustomize build overlay/apps02 | kubectl apply --server-side -f -
```

## Components

| Component | Description |
|-----------|-------------|
| `_forgejo` | Forgejo rootless server (StatefulSet, HTTP + SSH services, IngressRoute, certificate) |
| `_runner` | Forgejo Actions runner with Docker-in-Docker sidecar |

Enable components in the base `kustomization.yaml` (already wired):

```yaml
components:
  - ../components/_forgejo
  - ../components/_runner
```

## Configuration

### Key Placeholder Values

Replace these placeholders in patch and secret files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate-forgejo.yaml` | Organization name for TLS certificate |
| `###FQDN_OF_APPLICATION###` | `certificate-forgejo.yaml`, `ingressroute-forgejo.yaml` | External hostname (e.g. `git.home.essing.org`) |
| `###IP_ADDRESS_FOR_FORGEJO_SSH_FROM_METALLB_RANGE###` | `service-forgejo-ssh.yaml` | MetalLB IP for SSH LoadBalancer |
| `###PLACEHOLDER_DATABASE_PASSWORD###` | `secret-forgejo-database-user.env` | PostgreSQL password for the `forgejo` user |
| `###PLACEHOLDER_SMTP_USER###` | `secret-forgejo-config.env` | SMTP username / FROM address |
| `###PLACEHOLDER_SMTP_PASSWORD###` | `secret-forgejo-config.env` | SMTP password |
| `###PLACEHOLDER_RUNNER_REGISTRATION_TOKEN###` | `secret-forgejo-runner-token.env` | Runner registration token |

### Forgejo settings

The `secret-forgejo-config.env` file is generated as a `Secret` and consumed via `envFrom` so all
keys arrive as `FORGEJO__<section>__<KEY>` environment variables, which the rootless image renders
into `/etc/gitea/app.ini` on startup.

Key settings derived from the upstream documentation:

- **Database** — `postgres` over `require` SSL pointing at the central CNPG cluster, slow-query threshold reduced to 2s
  ([recommendations](https://forgejo.org/docs/latest/admin/setup/recommendations/)).
- **Storage** — local storage rooted at `/data` for attachments, LFS, repositories, packages, avatars, repo-archive,
  indexers, queues, sessions and logs ([storage](https://forgejo.org/docs/latest/admin/setup/storage/)).
- **Mailer** — SMTPS via env vars ([email](https://forgejo.org/docs/latest/admin/setup/email/)).
- **Security/Service** — install lock on, registration disabled, sign-in required, password complexity enforced,
  USERNAME_COOLDOWN_PERIOD=7, LOGIN_REMEMBER_DAYS=365.
- **Cache/UI/Repository** — `twoqueue` cache, `ONLY_SHOW_RELEVANT_REPOS=true`, signing trust model `committer`.
- **Actions** — enabled with `code.forgejo.org` as the default actions URL.

### Runner

The runner StatefulSet contains three containers:

1. **`runner-register`** (init): Runs `forgejo-runner register --no-interactive` against the in-cluster
   Forgejo service the first time the pod starts. The `.runner` registration file is persisted in the
   PVC, so subsequent starts skip registration.
2. **`runner`** (main): Runs `forgejo-runner daemon` using `/etc/forgejo-runner/config.yaml` from the
   ConfigMap. Talks to the DinD sidecar over `tcp://localhost:2376`.
3. **`dind`** (sidecar): `docker:dind` with `privileged: true`, sharing TLS certs via emptyDir.

Default labels exposed to Forgejo Actions: `docker:docker://node:20-bookworm`,
`ubuntu-latest:docker://node:20-bookworm`, `ubuntu-22.04:docker://node:20-bullseye`.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n forgejo
kubectl get statefulset -n forgejo
kubectl get pvc -n forgejo
```

### View Forgejo logs

```bash
kubectl logs -n forgejo statefulset/forgejo -c forgejo
```

### Verify database connectivity

```bash
kubectl exec -n forgejo forgejo-0 -c forgejo -- nc -zv postgres-database-rw.postgres.svc.apps02.home.essing.org 5432
```

### Check the runner

```bash
kubectl logs -n forgejo statefulset/forgejo-runner -c runner
kubectl logs -n forgejo statefulset/forgejo-runner -c dind
```

### Re-register the runner

Delete the runner's PVC content (or just the `.runner` file) and restart the StatefulSet so the
init container re-registers with a fresh token:

```bash
kubectl exec -n forgejo forgejo-runner-0 -c runner -- rm -f /data/.runner
kubectl rollout restart -n forgejo statefulset/forgejo-runner
```

## Related Resources

- [Forgejo Documentation](https://forgejo.org/docs/latest/)
- [Recommended Configuration](https://forgejo.org/docs/latest/admin/setup/recommendations/)
- [Email/Mailer Setup](https://forgejo.org/docs/latest/admin/setup/email/)
- [Storage Configuration](https://forgejo.org/docs/latest/admin/setup/storage/)
- [Forgejo Actions](https://forgejo.org/docs/latest/admin/actions/)
- [Forgejo Runner](https://code.forgejo.org/forgejo/runner)
- [Kustomize Documentation](https://kustomize.io/)
