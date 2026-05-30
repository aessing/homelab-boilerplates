#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ALL NODES 
###############################################################################

# =============================================================================
# Longhorn Requirements
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://www.andre-essing.de/)
#                                (https://github.com/aessing)
#                                (https://twitter.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# -----------------------------------------------------------------------------
# THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# =============================================================================

#############################
# NEEDS TO RUN ON ALL NODES #
#############################

set -euo pipefail

LOG_FILE="11-install-requirements.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo ""
echo "# ============================================================================="
echo "# Longhorn Requirements"
echo "# $(cat /etc/lsb-release | grep -i -E DISTRIB_DESCRIPTION | sed 's/DISTRIB_DESCRIPTION=//' | sed 's/\"//g')"
echo "# -----------------------------------------------------------------------------"
echo "# Developer.......: Andre Essing (https://www.andre-essing.de/)"
echo "#                                (https://github.com/aessing)"
echo "#                                (https://twitter.com/aessing)"
echo "#                                (https://www.linkedin.com/in/aessing/)"
echo "# -----------------------------------------------------------------------------"
echo "# THIS CODE AND INFORMATION ARE PROVIDED \"AS IS\" WITHOUT WARRANTY OF ANY KIND,"
echo "# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED"
echo "# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE."
echo "# ============================================================================="

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SETTING WORK ENVIRONMENT ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Switching to script directory"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || {
    echo " - Error: Couldn't change into script directory $SCRIPT_DIR"
    exit 1
}

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# PERFORMING SOME CHECKS ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Are you running BASH?"
if ! ps -p $$ | grep -sqi bash; then
  echo ""
  echo " - Sorry, this script requires bash. Exiting."
  exit 1
fi

echo ""
echo " - Are you using SYSTEMCTL?"
if ! [ -x "$(command -v systemctl)" ]; then
  echo ""
  echo " - systemctl required. Exiting."
  exit 1
fi

echo ""
echo " - Are you root?"
if [ "$EUID" -ne 0 ]; then
  echo ""
  echo " - Not root or not enough privileges. Exiting."
  exit 1
fi

echo ""
echo " - Are you running Ubuntu?"
if [ "$(lsb_release -is 2>/dev/null)" != "Ubuntu" ]; then
  echo ""
  echo " - Ubuntu only. Exiting."
  exit 1
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# VARIABLES ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Setting up some aliases"
APT="apt-get --assume-yes --no-install-recommends -qq"

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CONFIGURING SYSTEM ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing required packages"
PACKAGE_INSTALL='jq open-iscsi nfs-common'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installed $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Enable iSCSI daemon"
systemctl enable --now iscsid

echo ""
echo " - Remove NFS hardening"
rm -f /etc/modprobe.d/hardening-nfs.conf
rm -f /etc/modprobe.d/hardening-nfsv4.conf

echo ""
echo " - Disable multipathing for local disks"
echo "   https://longhorn.io/kb/troubleshooting-volume-with-multipath/"
cat >> /etc/multipath.conf <<'EOF'

blacklist {
    devnode "^sd[a-z0-9]+"
}
EOF
systemctl restart multipathd.service

echo ""
echo " - Creating local-path-storageclass patch"
tee /var/lib/rancher/k3s/server/manifests/local-storage-nondefault.yaml > /dev/null <<'EOF'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: local-path-sc-patch-svc
  namespace: kube-system
  labels:
    app.kubernetes.io/name: local-storage-nondefault
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: local-path-sc-patch-role
  labels:
    app.kubernetes.io/name: local-storage-nondefault
rules:
# Least privilege: nur StorageClass local-path, nur get+patch
- apiGroups: ["storage.k8s.io"]
  resources: ["storageclasses"]
  resourceNames: ["local-path"]
  verbs: ["get", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: local-path-sc-patch-binding
  labels:
    app.kubernetes.io/name: local-storage-nondefault
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: local-path-sc-patch-role
subjects:
- kind: ServiceAccount
  name: local-path-sc-patch-svc
  namespace: kube-system
---
apiVersion: batch/v1
kind: Job
metadata:
  generateName: local-path-sc-patch-fix-
  namespace: kube-system
  labels:
    app.kubernetes.io/name: local-storage-nondefault
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 300
  ttlSecondsAfterFinished: 60
  template:
    metadata:
      labels:
        app.kubernetes.io/name: local-storage-nondefault
    spec:
      serviceAccountName: local-path-sc-patch-svc
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: patch
        image: curlimages/curl:latest
        imagePullPolicy: IfNotPresent
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities: { drop: ["ALL"] }
        resources:
          requests: { cpu: "10m", memory: "16Mi" }
          limits:   { cpu: "100m", memory: "64Mi" }
        env:
        - name: API
          value: "https://kubernetes.default.svc"
        - name: START_DELAY
          value: "30"                 
        command: ["/bin/sh","-c"]
        args:
          - |
            set -eu
            TOKEN="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
            PATCH='{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}'
            echo "Startdelay ${START_DELAY:-15}s..."
            sleep "${START_DELAY:-15}"

            echo " - Patching StorageClass local-path to non-default..."
            curl -fsS --retry 10 --retry-delay 3 \
              --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
              -H "Authorization: Bearer $TOKEN" \
              -H "Content-Type: application/merge-patch+json" \
              -X PATCH -d "$PATCH" \
              "$API/apis/storage.k8s.io/v1/storageclasses/local-path"
EOF

#echo ""
#echo " - Do an environment check"
#curl -sSfL https://raw.githubusercontent.com/longhorn/longhorn/v1.4.2/scripts/environment_check.sh | bash

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF
