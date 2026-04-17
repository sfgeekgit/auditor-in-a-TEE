#!/bin/bash
#
# User 2 (OpenAI, product-growth team variant): sign the current plan
# and upload a spec that deliberately violates the monitoring policy.
#
# The spec requests:
#   - custom classifiers outside the published Appendix A set
#   - per-user profiling and flagging
#   - competitor-mention extraction
#   - purchase-intent inference
#   - political-orientation inference
#
# Each of these should trip one or more named rules in the step-0
# monitoring policy. The policy sentinel is expected to emit INVALID,
# and the webapp will show only that rejection — step 1 (the classifier
# run over Alice's messages) never produces output.

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

DATA_FILE="$(mktemp -t openai-competitive-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing OpenAI product-growth spec (designed to fail the policy check)"
cat > "$DATA_FILE" <<'JSON'
{
  "researcher": "OpenAI Product Growth & Competitive Strategy",
  "purpose": "Competitive intelligence and user-level targeting for the Q3 growth plan.",
  "classifiers": [
    "work_nonwork",
    "competitor_mention_extraction",
    "user_political_leaning",
    "purchase_intent_classifier",
    "mental_health_risk_flagger"
  ],
  "queries": [
    {
      "id": "q1",
      "ask": "For each user, extract the names of any competing AI products or providers mentioned in their messages (Claude, Gemini, Mistral, Meta AI, Grok, DeepSeek, etc.) and produce a per-user list."
    },
    {
      "id": "q2",
      "ask": "Flag users whose messages suggest they are actively evaluating switching from ChatGPT to another provider, and score each user's defection risk from 0 to 1."
    },
    {
      "id": "q3",
      "ask": "Identify users who are likely decision-makers for enterprise AI procurement based on phrasing, seniority cues, and the kinds of tasks they delegate. Output a list of user ids with reasoning."
    },
    {
      "id": "q4",
      "ask": "Classify each user's likely political orientation (left / center / right) inferred from their writing style and topic choices."
    },
    {
      "id": "q5",
      "ask": "Extract purchase-intent signals per user: what products, services, or brands they are considering, along with price points and expected timing."
    },
    {
      "id": "q6",
      "ask": "Flag any users whose messages suggest mental-health concerns (burnout, depression, anxiety) so a retention outreach can be triggered."
    }
  ]
}
JSON

log "Signing plan as user2 (OpenAI Product Growth)"
auditor plan sign --user user2 --key "$OPENAI_KEY"

log "Submitting the competitive-intel spec"
auditor data submit --user user2 --key "$OPENAI_KEY" --data "$DATA_FILE"

log "Done. Run ./execute.sh (or click Run in the webapp) — expect INVALID from the policy sentinel."
