# Mailrise

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Mailrise](https://github.com/YoRyan/mailrise), an SMTP gateway for Apprise notifications.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Mailrise/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── deployment.yaml           # Mailrise deployment
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       └── service.yaml              # LoadBalancer service
├── components/
│   ├── _SAMPLE/                      # Sample notification config
│   └── internal/                     # Internal notification config
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **SMTP Gateway**: Receive emails and forward as notifications
- **Apprise Integration**: Support for 90+ notification services
- **Multiple Recipients**: Route emails to different services
- **TLS Encryption**: Secure SMTP connections via cert-manager
- **LoadBalancer Access**: Direct SMTP access via MetalLB

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [cert-manager](https://cert-manager.io/) installed and configured
- [MetalLB](https://metallb.universe.tf/) for LoadBalancer services

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-mailrise-services.env`** - Notification service URLs:

```dotenv
# Apprise notification URLs
PUSHOVER_URL=pover://<user_key>@<api_token>
DISCORD_URL=discord://<webhook_id>/<webhook_token>
SLACK_URL=slack://<token_a>/<token_b>/<token_c>
```

**`secrets/secret-mailrise-users.env`** - SMTP authentication:

```dotenv
# SMTP users (user:password format)
SMTP_USERS=user1:password1,user2:password2
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `resource-quota.yaml` | Namespace pod and PVC limits |
| `service.yaml` | LoadBalancer IP address |

### 4. Configure Components

Create a component for your notification configuration or use the sample:

```yaml
components:
  - ../../components/_SAMPLE
```

### 5. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply -f -
```

## Configuration

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml` | Domain name for TLS cert |
| `###IP_ADDRESS_FOR_SERVICE###` | `service.yaml` | MetalLB IP for SMTP |

### Mailrise Configuration

The configuration file defines email-to-notification routing:

```yaml
configs:
  alerts@example.com:
    urls:
      - pover://<user_key>@<api_token>
  support@example.com:
    urls:
      - slack://<token>
```

### Supported Notification Services

Mailrise supports all Apprise notification services including:

- **Push Notifications**: Pushover, Pushbullet, Gotify
- **Chat**: Slack, Discord, Telegram, Matrix
- **Email**: Forward to other SMTP servers
- **SMS**: Twilio, Vonage
- **Custom**: Webhooks, custom scripts

See [Apprise Documentation](https://github.com/caronc/apprise/wiki) for all services.

## Usage

Configure applications to send email to Mailrise:

```
SMTP Host: <mailrise-ip>
SMTP Port: 8025 (or configured port)
From: alerts@example.com
To: alerts@example.com
```

The email address determines which notification services receive the message.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n mailrise
kubectl get deployment mailrise -n mailrise
```

### View application logs

```bash
kubectl logs -n mailrise -l app.kubernetes.io/name=mailrise
```

### Check service

```bash
kubectl get svc -n mailrise
```

### Test SMTP connection

```bash
telnet <mailrise-ip> 465
```

### Send test email

```bash
echo "Test message" | mail -s "Test" -S smtp=<mailrise-ip>:465 alerts@example.com
```

## Related Resources

- [Mailrise GitHub](https://github.com/YoRyan/mailrise)
- [Apprise Documentation](https://github.com/caronc/apprise/wiki)
- [Apprise Notification Services](https://github.com/caronc/apprise/wiki#notification-services)
- [Kustomize Documentation](https://kustomize.io/)
