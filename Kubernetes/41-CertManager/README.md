# cert-manager Certificate Management

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [cert-manager](https://cert-manager.io/) on a K3s cluster with Azure DNS for Let's Encrypt ACME DNS01 challenge validation.

## Contents

| Item | Description |
|------|-------------|
| `base/` | Base Kustomize manifests for cert-manager deployment |
| `overlay/` | Environment-specific overlay configurations |

## What is cert-manager?

cert-manager is a powerful and extensible X.509 certificate controller for Kubernetes. It automates the management and issuance of TLS certificates from various sources, including Let's Encrypt, HashiCorp Vault, Venafi, and self-signed certificates.

## Features

- **Let's Encrypt Integration**: Automated certificate issuance via ACME protocol
- **Azure DNS Challenge**: DNS01 challenge validation using Azure DNS zones
- **Staging & Production Issuers**: Separate ClusterIssuers for testing and production
- **Helm Deployment**: Installed via K3s HelmChart controller
- **Automatic Renewal**: Certificates are automatically renewed before expiration

## Prerequisites

- K3s cluster running
- `kubectl` access to the cluster
- Azure DNS zone configured for your domain
- Azure Service Principal with DNS Zone Contributor permissions
- Environment file configured in `../environments/`

## Directory Structure

```text
41-CertManager/
├── README.md
├── base/
│   ├── kustomization.yaml        # Base kustomization
│   ├── resources/
│   │   ├── namespace.yaml        # certmgr-system namespace
│   │   ├── helmchart.yaml        # HelmChart for cert-manager
│   │   ├── helmchartconfig.yaml  # HelmChart configuration
│   │   └── clusterissuers-default.yaml  # Let's Encrypt ClusterIssuers
│   ├── patches/
│   │   └── target-namespace.yaml # Namespace patch for HelmChart
│   └── transformers/
│       ├── helmchart.yaml        # Transformer for HelmChart
│       └── helmchartconfig.yaml  # Transformer for HelmChartConfig
└── overlay/
    └── _SAMPLE/
        ├── kustomization.yaml    # Sample overlay configuration
        ├── generators/
        │   └── letsencrypt-serviceprincipal.yaml  # Secret generator
        ├── patches/
        │   ├── version.yaml      # cert-manager version patch
        │   └── clusterissuers-default.yaml  # Azure DNS config patch
        └── secrets/
            └── letsencrypt-serviceprincipal.env  # Service principal secret
```

## Quick Start

### 1. Create Azure Service Principal

Create a Service Principal with DNS Zone Contributor permissions:

```bash
# Create service principal
az ad sp create-for-rbac --name cert-manager-dns01 --sdk-auth

# Note the output values:
# - appId (clientID)
# - password (clientSecret)
# - tenant (tenantID)

# Get your subscription ID
az account show --query id -o tsv

# Grant DNS Zone Contributor role
az role assignment create \
  --assignee <appId> \
  --role "DNS Zone Contributor" \
  --scope /subscriptions/<subscriptionId>/resourceGroups/<resourceGroupName>/providers/Microsoft.Network/dnszones/<zoneName>
```

### 2. Create Your Overlay

Copy the sample overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 3. Configure Azure DNS Settings

Edit `overlay/my-environment/patches/clusterissuers-default.yaml`:

```yaml
- op: replace
  path: /spec/acme/email
  value: admin@yourdomain.com
- op: replace
  path: /spec/acme/solvers/0/dns01/azureDNS/clientID
  value: your-service-principal-client-id
- op: replace
  path: /spec/acme/solvers/0/dns01/azureDNS/environment
  value: AzurePublicCloud
- op: replace
  path: /spec/acme/solvers/0/dns01/azureDNS/hostedZoneName
  value: yourdomain.com
- op: replace
  path: /spec/acme/solvers/0/dns01/azureDNS/resourceGroupName
  value: your-resource-group
- op: replace
  path: /spec/acme/solvers/0/dns01/azureDNS/subscriptionID
  value: your-subscription-id
- op: replace
  path: /spec/acme/solvers/0/dns01/azureDNS/tenantID
  value: your-tenant-id
```

### 4. Configure Service Principal Secret

Edit `overlay/my-environment/secrets/letsencrypt-serviceprincipal.env` with your Service Principal password:

```text
your-service-principal-password
```

**Important:** Add this file to `.gitignore` to prevent committing secrets.

### 5. Configure Version (Optional)

Edit `overlay/my-environment/patches/version.yaml` to set the cert-manager version:

```yaml
- op: replace
  path: /spec/version
  value: v1.19.1
```

### 6. Deploy cert-manager

```bash
# Preview the manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

### 7. Verify Installation

```bash
# Check cert-manager pods
kubectl get pods -n certmgr-system

# Check ClusterIssuers
kubectl get clusterissuers

# Check ClusterIssuer status
kubectl describe clusterissuer letsencrypt-production-default
kubectl describe clusterissuer letsencrypt-staging-default
```

## Using Certificates

### Request a Certificate

Create a Certificate resource:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: my-app-tls
  namespace: my-namespace
spec:
  secretName: my-app-tls-secret
  issuerRef:
    name: letsencrypt-production-default
    kind: ClusterIssuer
  dnsNames:
    - myapp.yourdomain.com
    - www.myapp.yourdomain.com
```

### Use with Ingress

Annotate your Ingress to automatically request certificates:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-production-default
spec:
  tls:
    - hosts:
        - myapp.yourdomain.com
      secretName: my-app-tls-secret
  rules:
    - host: myapp.yourdomain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 80
```

### Use with Traefik IngressRoute

For Traefik's native IngressRoute:

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: my-app
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`myapp.yourdomain.com`)
      kind: Rule
      services:
        - name: my-app
          port: 80
  tls:
    secretName: my-app-tls-secret
```

## Configuration Reference

### ClusterIssuer Fields

| Field | Description |
|-------|-------------|
| `spec.acme.email` | Email for Let's Encrypt account registration |
| `spec.acme.server` | ACME server URL (staging or production) |
| `spec.acme.privateKeySecretRef` | Secret to store ACME account private key |
| `spec.acme.solvers` | List of challenge solvers |

### Azure DNS Solver Fields

| Field | Description |
|-------|-------------|
| `clientID` | Azure Service Principal Application ID |
| `clientSecretSecretRef` | Reference to secret containing SP password |
| `subscriptionID` | Azure Subscription ID |
| `tenantID` | Azure Tenant ID |
| `resourceGroupName` | Resource group containing the DNS zone |
| `hostedZoneName` | DNS zone name (e.g., yourdomain.com) |
| `environment` | Azure environment (AzurePublicCloud, AzureGermanCloud, etc.) |

### HelmChartConfig Values

The base configuration sets these Helm values:

| Value | Description |
|-------|-------------|
| `installCRDs: true` | Install cert-manager CRDs |
| `replicaCount: 1` | cert-manager controller replicas |
| `cainjector.replicaCount: 1` | CA injector replicas |
| `webhook.replicaCount: 1` | Webhook replicas |
| `dns01RecursiveNameservers` | DNS servers for ACME challenges |
| `dns01RecursiveNameserversOnly: true` | Only use specified DNS servers |

## Troubleshooting

### Check cert-manager logs

```bash
kubectl logs -n certmgr-system -l app.kubernetes.io/component=controller
kubectl logs -n certmgr-system -l app.kubernetes.io/component=webhook
kubectl logs -n certmgr-system -l app.kubernetes.io/component=cainjector
```

### Check certificate status

```bash
# List all certificates
kubectl get certificates -A

# Describe a certificate
kubectl describe certificate <name> -n <namespace>

# Check certificate requests
kubectl get certificaterequests -A

# Check orders (ACME)
kubectl get orders -A

# Check challenges (ACME)
kubectl get challenges -A
```

### Common Issues

**ClusterIssuer not ready:**

- Verify Azure credentials are correct
- Check Service Principal has DNS Zone Contributor role
- Ensure the secret `letsencrypt-serviceprincipal` exists in `certmgr-system`

**Challenge stuck pending:**

- Verify DNS zone is publicly resolvable
- Check Azure DNS zone has correct delegation
- Ensure no firewall blocking DNS updates
- Check cert-manager logs for Azure API errors

**Certificate not issuing:**

- Start with staging issuer to avoid rate limits
- Check Order and Challenge resources for errors
- Verify domain ownership and DNS configuration

### Test with staging first

Always test with the staging ClusterIssuer first:

```yaml
issuerRef:
  name: letsencrypt-staging-default
  kind: ClusterIssuer
```

Staging certificates are not trusted but don't count against rate limits.

## Related Resources

- [cert-manager Documentation](https://cert-manager.io/docs/)
- [cert-manager GitHub Repository](https://github.com/cert-manager/cert-manager)
- [Let's Encrypt Rate Limits](https://letsencrypt.org/docs/rate-limits/)
- [Azure DNS01 Configuration](https://cert-manager.io/docs/configuration/acme/dns01/azuredns/)
- [K3s HelmChart Controller](https://docs.k3s.io/helm)
