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
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

set -euo pipefail

echo "🔍 Suche nach Pods mit PVCs in allen relevanten Namespaces..."

# Liste aller auszuschließenden Namespaces (Regex sicher)
excluded_namespaces="certmgr-system|kube-node-lease|kube-public|kube-system|kube-system|longhorn-system|metallb-system|multus-system|reloader-system|traefik-system"

# Hole alle Namespaces außer den ausgeschlossenen
namespaces=$(kubectl get ns -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep -Ev "^($excluded_namespaces)$")

for ns in $namespaces; do
    echo "📂 Namespace: $ns"

    # Hole alle Pods in diesem Namespace
    pods=$(kubectl get pods -n "$ns" -o jsonpath='{.items[*].metadata.name}')

    for pod in $pods; do
        # Prüfe, ob der Pod PVCs verwendet
        uses_pvc=$(kubectl get pod "$pod" -n "$ns" -o json | jq '.spec.volumes[]? | select(.persistentVolumeClaim != null)' | wc -l)

        if [[ "$uses_pvc" -gt 0 ]]; then
            echo "➡️  Pod mit PVC: $pod"

            # Hole alle Container im Pod
            containers=$(kubectl get pod "$pod" -n "$ns" -o jsonpath='{.spec.containers[*].name}')
            for container in $containers; do
                echo "  📦 Container: $container"
                kubectl exec -n "$ns" -c "$container" "$pod" -- df -h || echo "  ⚠️ Fehler beim Ausführen in $pod/$container"
                echo ""
            done
        fi
    done
done