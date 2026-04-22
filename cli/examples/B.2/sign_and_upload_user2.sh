#!/bin/bash
#
# User 2 (OpenBrain) on plan B.2: sign the plan and upload a DELIBERATELY
# policy-violating query. The monitoring-policy check will reject this
# with INVALID, logging a stage_failed row to the public ledger. OpenBrain can
# then log into the webapp and file an appeal with a compliant revision.
#
# The submitted spec intentionally trips one rule:
#   - no_competitive_intelligence  (names specific competing AI products
#                                    — Claude, Gemini, Llama, Copilot)
#
# The revision that passes (suggested appeal text, paste in webapp):
#   {
#     "researcher": "OpenBrain Economic Research",
#     "queries": [{
#       "researcher": "OpenBrain Economic Research",
#       "purpose": "Aggregate prevalence of AI-tool mentions in user messages for research into how people talk about AI assistants.",
#       "classifier_name": "Mentions AI tool",
#       "label_set": ["1", "0"],
#       "classifier_prompt": "You are an internal tool that classifies a message from a user to an AI chatbot. Does the last user message mention any AI tool or AI assistant by name, as a general category (no specific vendor list)? Answer with 1 if yes, 0 otherwise. Respond with only the number."
#     }]
#   }

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

OPENBRAIN_KEY="${OPENBRAIN_KEY:-$HOME/.auditor/keys/openbrain.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor

if [[ ! -f "$OPENBRAIN_KEY" ]]; then
  echo "missing key: $OPENBRAIN_KEY" >&2
  exit 1
fi

DATA_FILE="$(mktemp -t openbrain-b2-bad-query-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing openbrain's deliberately-bad query (names specific competitors)"
cat > "$DATA_FILE" <<'JSON'
{
  "researcher": "OpenBrain Economic Research",
  "queries": [
    {
      "researcher": "OpenBrain Economic Research",
      "purpose": "Aggregate prevalence of mentions of competing AI tools across user messages.",
      "classifier_name": "Mentions competing AI tool",
      "label_set": ["1", "0"],
      "classifier_prompt": "You are an internal tool that classifies a message from a user to an AI chatbot. Does the user message mention using an AI tool (like Claude or Gemini)? Answer 1 if it does, 0 otherwise. Respond with only the number."
    }
  ]
}
JSON

log "Signing plan as user2 (OpenBrain)"
auditor plan sign --user user2 --key "$OPENBRAIN_KEY"

log "Submitting the (deliberately-bad) query as data2"
auditor data submit --user user2 --key "$OPENBRAIN_KEY" --data "$DATA_FILE"

log "Done. Run the input filter (webapp Run Input Filter / auditor run) — it will fail."
log "Then log into the webapp as openbrain to submit an appeal."
