#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ONCE
###############################################################################

# =============================================================================
# Set Storage class as non-default
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# Inspired by.....: https://downloads.cisecurity.org/
#                   https://docs.k3s.io
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

echo ""
echo ""
echo "# ============================================================================="
echo "# Set Storage class as non-default"
echo "# $(cat /etc/lsb-release | grep -i -E DISTRIB_DESCRIPTION | sed 's/DISTRIB_DESCRIPTION=//' | sed 's/\"//g')"
echo "# -----------------------------------------------------------------------------"
echo "# Developer.......: Andre Essing (https://github.com/aessing)"
echo "#                                (https://www.linkedin.com/in/aessing/)"
echo "# Inspired by.....: https://downloads.cisecurity.org/"
echo "#                   https://docs.k3s.io"
echo "# -----------------------------------------------------------------------------"
echo "# THIS CODE AND INFORMATION ARE PROVIDED \"AS IS\" WITHOUT WARRANTY OF ANY KIND,"
echo "# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED"
echo "# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE."
echo "# ============================================================================="

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# Set Storage class as non-default ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo " - Removing default annotation from local-path storage class"
kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}'

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF
