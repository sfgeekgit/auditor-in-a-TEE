#!/bin/bash
#
# User 2 (Bob, the lender) on plan D.1: co-sign the plan. The underwriting
# rule (40% max-counterparty threshold) is agreed via the plan itself, not
# uploaded — so Bob is a co-signer only. The TEE no longer requires a
# placeholder upload for unused slots.

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

log "Signing plan as user2 (Bob, the lender — co-signer only, no data required)"
auditor plan sign --user user2 --key "$BOB_KEY"

log "Done. Plan should now be data_ready — run ./execute.sh."
