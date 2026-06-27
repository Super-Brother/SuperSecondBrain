#!/usr/bin/env bash
set -euo pipefail

# Host-side sync helper for Docker server deployments.
#
# The API container may not include git, so the host pulls the vault repository
# and then asks the running API process to rebuild the index incrementally.

VAULT_PATH="${VAULT_PATH:-/home/zwc/super-second-brain}"
API_URL="${API_URL:-http://localhost:8001}"

git -C "$VAULT_PATH" pull --ff-only

curl -fsS \
  -X POST "$API_URL/api/v1/sync/trigger" \
  -H "Content-Type: application/json" \
  -d '{"incremental":true}'

echo
