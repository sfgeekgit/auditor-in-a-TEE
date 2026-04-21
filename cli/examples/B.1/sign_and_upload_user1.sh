#!/bin/bash
#
# User 1 (Alice) on plan B.1 (Monitor Query Validation): sign the plan and
# upload a placeholder as data1. This plan doesn't use user 1's data — Alice
# is a co-signer only — but the TEE still requires both parties to submit
# something before running.
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

DATA_FILE="$(mktemp -t alice-b1-placeholder-XXXXXX.txt)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing placeholder data1 (unused by this plan)"
printf 'unused' > "$DATA_FILE"

log "Signing plan as user1 (Alice)"
auditor plan sign --user user1 --key "$ALICE_KEY"

log "Submitting placeholder as user1 data"
auditor data submit --user user1 --key "$ALICE_KEY" --data "$DATA_FILE"

log "Done. Plan still needs user2 to sign + submit the queries."
