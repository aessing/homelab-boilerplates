# trust-manager CA Bundle Distribution

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [trust-manager](https://cert-manager.io/docs/trust/trust-manager/) on a K3s cluster to distribute trusted CA certificates across namespaces.

## Contents

| Item | Description |
|------|-------------|
| `base/` | Base Kustomize manifests for trust-manager deployment |
| `overlay/` | Environment-specific overlay configurations |

## What is trust-manager?

trust-manager is a Kubernetes operator that distributes trust bundles (CA certificates) to workloads running in your cluster. It is designed to work alongside cert-manager to provide a complete PKI solution.

## Features

- **CA Bundle Distribution**: Automatically distribute CA certificates to namespaces
- **Default CAs**: Include system default CA certificates in bundles
- **Namespace Selector**: Target specific namespaces with label selectors
- **Secret Targets**: Create secrets containing CA bundles for applications
- **Helm Deployment**: Installed via K3s HelmChart controller

## Prerequisites

- K3s cluster running
- cert-manager installed (trust-manager is part of the cert-manager project)
- `kubectl` access to the cluster
- Environment file configured in `../environments/`

## Directory Structure

```text
42-TrustManager/
├── README.md
├── base/
│   ├── kustomization.yaml        # Base kustomization
│   ├── resources/
│   │   ├── namespace.yaml        # certmgr-trust namespace
│   │   ├── helmchart.yaml        # HelmChart for trust-manager
│   │   ├── helmchartconfig.yaml  # HelmChart configuration
│   │   └── bundle.yaml           # Default CA bundle definition
│   ├── patches/
│   │   └── target-namespace.yaml # Namespace patch for HelmChart
│   └── transformers/
│       ├── helmchart.yaml        # Transformer for HelmChart
│       └── helmchartconfig.yaml  # Transformer for HelmChartConfig
└── overlay/
    └── _SAMPLE/
        ├── kustomization.yaml    # Sample overlay configuration
        └── patches/
            └── version.yaml      # trust-manager version patch
```

## Quick Start

### 1. Ensure cert-manager is Installed

trust-manager requires cert-manager CRDs. Deploy cert-manager first using the `41-CertManager` folder.

### 2. Create Your Overlay

Copy the sample overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 3. Configure Version (Optional)

Edit `overlay/my-environment/patches/version.yaml` to set the trust-manager version:

```yaml
- op: replace
  path: /spec/version
  value: v0.20.2
```

### 4. Deploy trust-manager

```bash
# Preview the manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

### 5. Verify Installation

```bash
# Check trust-manager pods
kubectl get pods -n certmgr-system -l app.kubernetes.io/name=trust-manager

# Check Bundle resource
kubectl get bundles

# Describe the default bundle
kubectl describe bundle trust-manager-ca
```

## Using Trust Bundles

### Enable CA Bundle in a Namespace

Label your namespace to receive the CA bundle:

```bash
kubectl label namespace my-namespace workspace.trust.cert-manager.io/trust-manager-ca=true
```

This creates a secret named `trust-manager-ca` in the namespace containing the CA certificates.

### Use in Applications

Mount the CA bundle secret in your pods:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
spec:
  containers:
    - name: app
      image: my-app:latest
      volumeMounts:
        - name: ca-bundle
          mountPath: /etc/ssl/certs/ca-certificates.crt
          subPath: ca.crt
          readOnly: true
  volumes:
    - name: ca-bundle
      secret:
        secretName: trust-manager-ca
```

### Create Custom Bundles

Create additional bundles for specific use cases:

```yaml
apiVersion: trust.cert-manager.io/v1alpha1
kind: Bundle
metadata:
  name: my-custom-ca
spec:
  sources:
    - useDefaultCAs: true
    - secret:
        name: my-private-ca
        key: ca.crt
  target:
    secret:
      key: ca-bundle.crt
    namespaceSelector:
      matchLabels:
        my-app.example.com/ca-bundle: "true"
```

## Configuration Reference

### Bundle Sources

| Source Type | Description |
|-------------|-------------|
| `useDefaultCAs: true` | Include system default CA certificates |
| `secret` | Include CA from a Kubernetes secret |
| `configMap` | Include CA from a ConfigMap |
| `inLine` | Include inline PEM-encoded CA certificate |

### Bundle Target Options

| Field | Description |
|-------|-------------|
| `target.secret.key` | Key name in the generated secret |
| `target.configMap.key` | Key name in the generated ConfigMap |
| `target.namespaceSelector` | Label selector for target namespaces |

### HelmChartConfig Values

The base configuration sets these Helm values:

| Value | Description |
|-------|-------------|
| `replicaCount: 1` | trust-manager replicas (2 for HA) |
| `revisionHistoryLimit: 3` | Old ReplicaSets to retain |
| `secretTargets.enabled: true` | Enable secret target support |
| `secretTargets.authorizedSecrets` | List of allowed secret names |
| `app.trust.namespace` | Namespace for trust resources |

## Troubleshooting

### Check trust-manager logs

```bash
kubectl logs -n certmgr-system -l app.kubernetes.io/name=trust-manager
```

### Check bundle status

```bash
# List all bundles
kubectl get bundles

# Describe a bundle
kubectl describe bundle trust-manager-ca

# Check if secret was created in namespace
kubectl get secret trust-manager-ca -n my-namespace
```

### Common Issues

**Secret not created in namespace:**

- Verify namespace has the correct label
- Check bundle's `namespaceSelector` matches
- Ensure secret name is in `authorizedSecrets` list

**Bundle shows error status:**

- Check trust-manager logs for errors
- Verify source secrets/ConfigMaps exist
- Ensure proper RBAC permissions

**CA certificates not updated:**

- trust-manager watches for changes automatically
- Check bundle status for sync errors
- Verify source CA has not expired

## Related Resources

- [trust-manager Documentation](https://cert-manager.io/docs/trust/trust-manager/)
- [trust-manager GitHub Repository](https://github.com/cert-manager/trust-manager)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [K3s HelmChart Controller](https://docs.k3s.io/helm)
