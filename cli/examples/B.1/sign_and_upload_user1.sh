#!/bin/bash
#
# User 1 (Alice) on plan B.1 (Monitor Query Validation): co-sign the plan.
# Alice's data isn't read by any step in this plan, so she has no data to
# upload — the TEE no longer requires a placeholder for unused slots.
#
# Run plan_creation.sh first — the CLI state file remembers the plan_id.

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor

if [[ ! -f "$ALICE_KEY" ]]; then
  echo "missing key: $ALICE_KEY" >&2
  exit 1
fi

log "Signing plan as user1 (Alice — co-signer only, no data required)"
auditor plan sign --user user1 --key "$ALICE_KEY"

log "Done. Plan still needs user2 to sign + submit the queries."
