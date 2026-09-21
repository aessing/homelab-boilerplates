#!/usr/bin/env bash

# =============================================================================
# Helper Script: checkVolumes.sh
# Checks the usage of Persistent Volume Claims (PVCs) in all relevant 
# Kubernetes namespaces.
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# Inspired by.....: ChatGPT (https://chat.openai.com/)
# -----------------------------------------------------------------------------
# THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# =============================================================================

set -euo pipefail

echo "🔍 Searching for pods with PVCs in all relevant namespaces..."

# List of all excluded namespaces (Regex-safe)
excluded_namespaces="certmgr-system|kube-node-lease|kube-public|kube-system|longhorn-system|metallb-system|multus-system|reloader-system|traefik-system"

# Get all namespaces except the excluded ones
namespaces=$(kubectl get ns -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep -Ev "^($excluded_namespaces)$")

for ns in $namespaces; do
    echo "📂 Namespace: $ns"

    # Get all pods in this namespace
    pods=$(kubectl get pods -n "$ns" -o jsonpath='{.items[*].metadata.name}')

    for pod in $pods; do
        # Check if the pod uses PVCs
        uses_pvc=$(kubectl get pod "$pod" -n "$ns" -o json | jq '.spec.volumes[]? | select(.persistentVolumeClaim != null)' | wc -l)

        if [[ "$uses_pvc" -gt 0 ]]; then
            echo "➡️  Pod with PVC: $pod"

            # Get all containers in the pod
            containers=$(kubectl get pod "$pod" -n "$ns" -o jsonpath='{.spec.containers[*].name}')
            for container in $containers; do
                echo "  📦 Container: $container"
                kubectl exec -n "$ns" -c "$container" "$pod" -- df -h || echo "  ⚠️ Error executing in $pod/$container"
                echo ""
            done
        fi
    done
done
