# PostgreSQL (CloudNativePG)

This folder contains Kustomize manifests for deploying a highly available PostgreSQL database cluster using [CloudNativePG (CNPG)](https://cloudnative-pg.io/) on Kubernetes.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
PostgreSQL/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── certificate.yaml          # TLS certificate for secure connections
│       ├── cluster.yaml              # CNPG Cluster definition
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy-clients.yaml    # Network policy for client access
│       ├── network-policy-cnpg.yaml       # Network policy for CNPG operator
│       ├── network-policy-instance.yaml   # Network policy between instances
│       ├── network-policy-kubeproxy.yaml  # Network policy for kube-proxy
│       ├── object-store.yaml         # S3-compatible backup storage config
│       ├── resource-quota.yaml       # Namespace resource quotas
│       └── scheduled-backup.yaml     # Automated backup schedule
└── overlay/
    └── _SAMPLE/                      # Template overlay for new deployments
        ├── kustomization.yaml
        ├── databases/                # Database and role definitions
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        └── secrets/                  # Secret environment files
```

## Features

- **High Availability**: Multi-instance PostgreSQL cluster with synchronous replication
- **TLS Encryption**: Secure connections using cert-manager certificates
- **External Access**: LoadBalancer services via MetalLB for read-write, read-only, and replica endpoints
- **Automated Backups**: Scheduled backups to S3-compatible object storage (e.g., Backblaze B2)
- **Network Policies**: Granular network security controls
- **Declarative Databases**: Manage databases and roles via Kubernetes CRDs

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [CloudNativePG Operator](https://cloudnative-pg.io/documentation/current/installation_upgrade/) installed
- [cert-manager](https://cert-manager.io/) installed and configured
- [trust-manager](https://cert-manager.io/docs/trust/trust-manager/) with a CA secret named `trust-manager-ca`
- [MetalLB](https://metallb.universe.tf/) configured for LoadBalancer services
- S3-compatible object storage for backups (optional but recommended)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-superuser.env`** - PostgreSQL superuser credentials:

```dotenv
username=postgres
password=<your-secure-password>
```

**`secrets/secret-initdb.env`** - Initial database user:

```dotenv
username=initdb
password=<your-secure-password>
```

**`secrets/secret-objectstore.env`** - S3 backup storage credentials:

```dotenv
ACCESS_KEY_ID=<your-access-key-id>
ACCESS_KEY_NAME=<your-access-key-name>
ACCESS_SECRET_KEY=<your-secret-key>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory to customize your deployment:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `cluster-instance.yaml` | Instance count, PostgreSQL version, sync replicas |
| `cluster-loadbalancer.yaml` | MetalLB IP addresses for external services |
| `cluster-locale.yaml` | Locale and encoding settings |
| `cluster-resources.yaml` | CPU, memory limits, storage size, shared_buffers |
| `network-policy-clients.yaml` | Allowed client IP ranges |
| `network-policy-kubeproxy.yaml` | Kube-proxy access rules |
| `object-store.yaml` | S3 bucket and endpoint configuration |
| `resource-quota.yaml` | Namespace resource quotas |
| `scheduled-backup.yaml` | Backup schedule (cron format) |

### 4. Configure Databases and Roles

Edit the files in your overlay's `databases/` directory:

**`databases/roles.yaml`** - Define database users/roles with their permissions and password secrets.

**`databases/databases.yaml`** - Define databases, their owners, schemas, and extensions.

**`databases/secrets.yaml`** - Secret generators for database user credentials.

**`databases/secret-*.env`** - Environment files with database user credentials.

### 5. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply -f -
```

## The _SAMPLE Overlay Explained

The `_SAMPLE` overlay is a template that demonstrates how to configure a PostgreSQL cluster. It contains placeholder values (marked with `###...###`) that you must replace with your actual configuration.

### Directory Structure

```text
_SAMPLE/
├── kustomization.yaml      # Main kustomization file referencing all resources
├── databases/
│   ├── databases.yaml      # Database definitions (app01, app02 examples)
│   ├── roles.yaml          # Role definitions with permissions
│   ├── secrets.yaml        # Secret generators for database users
│   ├── secret-app01.env    # Credentials for app01 user
│   └── secret-app02.env    # Credentials for app02 user
├── generators/
│   ├── secret-initdb.yaml      # Generator for initdb secret
│   ├── secret-objectstore.yaml # Generator for S3 credentials
│   └── secret-superuser.yaml   # Generator for superuser secret
├── patches/
│   ├── certificate.yaml         # TLS certificate customization
│   ├── cluster-instance.yaml    # Instance count and PG version
│   ├── cluster-loadbalancer.yaml # MetalLB IPs
│   ├── cluster-locale.yaml      # Locale settings
│   ├── cluster-resources.yaml   # Resource limits
│   ├── network-policy-clients.yaml  # Client network access
│   ├── network-policy-kubeproxy.yaml # Kube-proxy access
│   ├── object-store.yaml        # Backup storage config
│   ├── resource-quota.yaml      # Namespace quotas
│   └── scheduled-backup.yaml    # Backup schedule
└── secrets/
    ├── secret-initdb.env        # initdb user password
    ├── secret-objectstore.env   # S3 access keys
    └── secret-superuser.env     # Superuser password
```

### Key Configuration Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###INSTANCE_COUNT(3)###` | `cluster-instance.yaml` | Number of PostgreSQL instances (3 recommended for HA) |
| `###SYNCHRONOUS_REPLICAS(1)###` | `cluster-instance.yaml` | Number of synchronous replicas |
| `###PGSQL_VERSION###` | `cluster-instance.yaml` | PostgreSQL major version (16, 17, 18) |
| `###LOAD_BALANCER_IP_RW###` | `cluster-loadbalancer.yaml` | IP for read-write service |
| `###LOAD_BALANCER_IP_RO###` | `cluster-loadbalancer.yaml` | IP for read-only service |
| `###LOAD_BALANCER_IP_R###` | `cluster-loadbalancer.yaml` | IP for replica service |
| `###PVC_SIZE###` | `cluster-resources.yaml` | Storage size (e.g., `16Gi`) |
| `###MEMORY_REQUEST###` | `cluster-resources.yaml` | Memory request (e.g., `1024Mi`) |
| `###CPU_REQUEST###` | `cluster-resources.yaml` | CPU request (e.g., `0.5`) |
| `###MEMORY_LIMIT###` | `cluster-resources.yaml` | Memory limit (e.g., `2048Mi`) |
| `###CPU_LIMIT###` | `cluster-resources.yaml` | CPU limit (e.g., `1`) |
| `###SHARED_BUFFERS###` | `cluster-resources.yaml` | PostgreSQL shared_buffers (~25% of RAM) |
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN###` | `certificate.yaml` | External domain name |
| `###CLUSTER_FQDN###` | `certificate.yaml` | Cluster internal domain |
| `###BUCKET###` | `object-store.yaml` | S3 bucket name |
| `###ENDPOINT_URL###` | `object-store.yaml` | S3 endpoint URL |

## Adding Databases and Roles

To add a new application database:

1. Add the role definition to `databases/roles.yaml`
2. Add the database definition to `databases/databases.yaml`
3. Create a secret env file: `databases/secret-<appname>.env`
4. Add the secret generator to `databases/secrets.yaml`

After applying the configuration, run the following SQL commands to secure database access:

```sql
REVOKE CONNECT ON DATABASE <database_name> FROM PUBLIC;
GRANT CONNECT ON DATABASE <database_name> TO <role_name>;
```

## Network Policies

The deployment includes several network policies for security:

- **clients-to-database**: Controls which IP ranges can connect to the database
- **cnpg**: Allows CNPG operator communication
- **instance**: Allows communication between PostgreSQL instances
- **kubeproxy**: Allows health checks from kube-proxy

Customize `patches/network-policy-clients.yaml` to define your allowed client IP ranges.

## Backups

Backups are configured to use S3-compatible object storage via the Barman Cloud plugin:

1. Configure S3 credentials in `secrets/secret-objectstore.env`
2. Set the bucket and endpoint in `patches/object-store.yaml`
3. Configure the backup schedule in `patches/scheduled-backup.yaml`

The schedule uses cron format: `seconds minutes hours day month weekday`

## Troubleshooting

### Check cluster status

```bash
kubectl get cluster -n postgres
kubectl describe cluster postgres-database -n postgres
```

### View pod logs

```bash
kubectl logs -n postgres -l cnpg.io/cluster=postgres-database
```

### Check backup status

```bash
kubectl get scheduledbackup -n postgres
kubectl get backup -n postgres
```

### CNPG Plugin Commands

The [kubectl-cnpg plugin](https://cloudnative-pg.io/documentation/current/kubectl-plugin/) provides additional commands for managing CNPG clusters:

```bash
# Get cluster status with detailed information
kubectl cnpg status postgres-database -n postgres

# Promote a replica to primary (for planned switchover)
kubectl cnpg promote postgres-database <pod-name> -n postgres

# Trigger an on-demand backup
kubectl cnpg backup postgres-database --method plugin --plugin-name barman-cloud.cloudnative-pg.io -n postgres 

# Restart the cluster (rolling restart)
kubectl cnpg restart postgres-database -n postgres

# Reload PostgreSQL configuration
kubectl cnpg reload postgres-database -n postgres

# Open a psql shell to the primary
kubectl cnpg psql postgres-database -n postgres

# Check cluster logs
kubectl cnpg logs cluster postgres-database -n postgres

# Hibernate the cluster (scale down to zero)
kubectl cnpg hibernate on postgres-database -n postgres

# Wake up the cluster from hibernation
kubectl cnpg hibernate off postgres-database -n postgres

# Generate a connection string
kubectl cnpg connection postgres-database -n postgres
```

## Related Resources

- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Kustomize Documentation](https://kustomize.io/)
