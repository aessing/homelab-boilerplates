#!/usr/bin/env bash

# =============================================================================
# Helper Script: setLonghornTrimOnly.sh
# Sets the label 'recurring-job-group.longhorn.io/longhorn-job-trim-weekly=enabled'
# on a specified Longhorn volume
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

# Colors
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
CYAN='\033[1;36m'
NC='\033[0m' # No Color

# Check for required parameter
if [ "$#" -ne 1 ]; then
  echo -e "${YELLOW}❌ Usage: $0 <volume-name>${NC}\n"
  exit 1
fi

VOLUME_NAME="$1"
NAMESPACE="longhorn-system"

echo -e "${CYAN}\n==============================================="
echo -e "🚀 Longhorn Volume Label Setter"
echo -e "===============================================${NC}\n"
echo -e ""

echo -e "${YELLOW}🔖 Setting label 'recurring-job-group.longhorn.io/longhorn-job-trim-weekly=enabled' on volume ${VOLUME_NAME}...${NC}"
kubectl -n "$NAMESPACE" label volume "$VOLUME_NAME" recurring-job-group.longhorn.io/longhorn-job-trim-weekly=enabled --overwrite
echo -e ""

echo -e "${YELLOW}🧹 Removing label 'recurring-job-group.longhorn.io/default' from volume ${VOLUME_NAME}...${NC}"
kubectl -n "$NAMESPACE" label volume "$VOLUME_NAME" recurring-job-group.longhorn.io/default-
echo -e ""

echo -e "\n${GREEN}✅ All done! Labels updated for volume ${VOLUME_NAME}.${NC}\n"
echo -e ""
