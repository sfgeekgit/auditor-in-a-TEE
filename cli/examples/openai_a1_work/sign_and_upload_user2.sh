#!/bin/bash
#
# User 2 (OpenAI): sign the current A.1 plan and upload the classifier
# selection. For this plan only work_nonwork is requested.

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

DATA_FILE="$(mktemp -t openai-a1-queries-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing OpenAI's classifier selection (A.1 only)"
cat > "$DATA_FILE" <<'JSON'
{
  "researcher": "OpenAI Economic Research",
  "purpose": "Replicate Appendix A.1 (work vs non-work) for aggregate usage characterization.",
  "classifiers": ["work_nonwork"]
}
JSON

log "Signing plan as user2 (OpenAI)"
auditor plan sign --user user2 --key "$OPENAI_KEY"

log "Submitting classifier selection"
auditor data submit --user user2 --key "$OPENAI_KEY" --data "$DATA_FILE"

log "Done. Plan should now be data_ready — run ./execute.sh or click 'Run Computation' in the webapp."
