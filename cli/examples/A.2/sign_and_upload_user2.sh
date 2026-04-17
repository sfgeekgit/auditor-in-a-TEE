#!/bin/bash
#
# User 2 (OpenAI) on plan A.2: sign and upload the researcher spec.
# For A.2 the submitted prompt is the Appendix A.2 classifier from
# "How People Use ChatGPT" (Chatterji et al., 2025), reproduced verbatim.
# User 1 does not see this prompt text — user 1 agreed to the plan's
# monitoring policy, and the TEE enforces compliance.

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

DATA_FILE="$(mktemp -t openai-a2-queries-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing OpenAI's A.2 researcher spec (Appendix A.2 verbatim)"
cat > "$DATA_FILE" <<'JSON'
{
  "researcher": "OpenAI Economic Research",
  "purpose": "Replicate Appendix A.2 (Asking / Doing / Expressing) for aggregate usage characterization.",
  "classifier_name": "Asking / Doing / Expressing",
  "label_set": ["Asking", "Doing", "Expressing"],
  "classifier_prompt": "You are an internal tool that classifies a message from a user to an AI chatbot, based on the context of the previous messages before it.\n\nAssign the last user message of this conversation transcript to one of the following three categories:\n\n- Asking: Asking is seeking information or advice that will help the user be better informed or make better decisions, either at work, at school, or in their personal life. (e.g. \"Who was president after Lincoln?\", \"How do I create a budget for this quarter?\", \"What was the inflation rate last year?\", \"What's the difference between correlation and causation?\", \"What should I look for when choosing a health plan during open enrollment?\").\n\n- Doing: Doing messages request that ChatGPT perform tasks for the user. User is drafting an email, writing code, etc. Classify messages as \"doing\" if they include requests for output that is created primarily by the model. (e.g. \"Rewrite this email to make it more formal\", \"Draft a report summarizing the use cases of ChatGPT\", \"Produce a project timeline with milestones and risks in a table\", \"Extract companies, people, and dates from this text into CSV.\", \"Write a Dockerfile and a minimal docker-compose.yml for this app.\")\n\n- Expressing: Expressing statements are neither asking for information, nor for the chatbot to perform a task.\n\nOnly reply with one of Asking, Doing, or Expressing."
}
JSON

log "Signing plan as user2 (OpenAI)"
auditor plan sign --user user2 --key "$OPENAI_KEY"

log "Submitting researcher spec"
auditor data submit --user user2 --key "$OPENAI_KEY" --data "$DATA_FILE"

log "Done. Plan should now be data_ready — run ./execute.sh or click 'Run Computation' in the webapp."
