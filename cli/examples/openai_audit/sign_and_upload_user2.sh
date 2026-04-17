#!/bin/bash
#
# User 2 (OpenAI): sign the current plan and upload the classifier selection.
# Run openai_plan_creation.sh first — the CLI state file remembers the plan_id.
#
# Env:
#   AUDITOR_TEE_URL   defaults to the Ben deployment
#   OPENAI_KEY        defaults to ~/.auditor/keys/openai.json

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

OPENAI_KEY="${OPENAI_KEY:-$HOME/.auditor/keys/openai.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor

if [[ ! -f "$OPENAI_KEY" ]]; then
  echo "missing key: $OPENAI_KEY" >&2
  exit 1
fi

DATA_FILE="$(mktemp -t openai-queries-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing OpenAI's classifier selection"
cat > "$DATA_FILE" <<'JSON'
{
  "researcher": "OpenAI Economic Research",
  "classifiers": [
    "work_nonwork",
    "asking_doing_expressing",
    "conversation_topic"
  ]
}
JSON

log "Signing plan as user2 (OpenAI)"
auditor plan sign --user user2 --key "$OPENAI_KEY"

log "Submitting classifier selection"
auditor data submit --user user2 --key "$OPENAI_KEY" --data "$DATA_FILE"

log "Done. Plan should now be data_ready — run ./execute.sh or click 'Run Computation' in the webapp."
