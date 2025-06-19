#!/bin/sh

# =============================================================================
# Prepare TLS JSON file for Scrypted App
# Scrypted
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# -----------------------------------------------------------------------------
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

echo "Converting TLS certificates to JSON format for Scrypted App..."
echo " - Current date and time: $(date)"

echo "{" > /server/volume/cert.json
awk 'BEGIN { printf "    \"key\": \""}; NF {sub(/\r\n/, ""); printf "%s\\r\\n",$0;}; END { printf "\",\n"};' /tls.key >> /server/volume/cert.json
awk 'BEGIN { printf "    \"cert\": \""}; NF {sub(/\r\n/, ""); printf "%s\\r\\n",$0;}; END { printf "\"\n"};' /tls.crt >> /server/volume/cert.json
echo "}" >> /server/volume/cert.json

echo " - TLS JSON file created at /server/volume/cert.json"