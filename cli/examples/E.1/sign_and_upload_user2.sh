#!/bin/bash
#
# User 2 (Bob) on plan E.1: sign the plan and upload his narrow topic
# question. Bob wants a single yes/no answer about whether any redaction
# mentions trading stocks — no details, no excerpts, nothing beyond the
# verdict.

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

DATA_FILE="$(mktemp -t bob-e1-question-XXXXXX.txt)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing Bob's narrow topic question"
cat > "$DATA_FILE" <<'TXT'
Do any of the redactions in the submitted email corpus mention trading
stocks — buying or selling shares, brokerage orders, trade confirmations,
or related securities activity? Answer with a single YES or NO.
TXT

log "Signing plan as user2 (Bob)"
auditor plan sign --user user2 --key "$BOB_KEY"

log "Submitting the topic question"
auditor data submit --user user2 --key "$BOB_KEY" --data "$DATA_FILE"

log "Done. Plan should now be data_ready — run ./execute.sh."
