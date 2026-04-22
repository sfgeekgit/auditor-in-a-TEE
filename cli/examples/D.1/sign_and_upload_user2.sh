#!/bin/bash
#
# User 2 (Bob, the lender) on plan D.1: sign the plan and upload a
# placeholder as data2. The underwriting rule (40% max-counterparty
# threshold) is agreed via the plan itself, not uploaded — so Bob is a
# co-signer only. The TEE still requires both parties to submit
# something before running, so we upload the literal string "co-signed".

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

BOB_KEY="${BOB_KEY:-$HOME/.auditor/keys/bob.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor

if [[ ! -f "$BOB_KEY" ]]; then
  echo "missing key: $BOB_KEY" >&2
  exit 1
fi

DATA_FILE="$(mktemp -t bob-d1-placeholder-XXXXXX.txt)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing placeholder data2 (Bob is a co-signer only)"
printf 'co-signed' > "$DATA_FILE"

log "Signing plan as user2 (Bob, the lender)"
auditor plan sign --user user2 --key "$BOB_KEY"

log "Submitting placeholder as user2 data"
auditor data submit --user user2 --key "$BOB_KEY" --data "$DATA_FILE"

log "Done. Plan should now be data_ready — run ./execute.sh."
