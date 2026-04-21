#!/bin/bash
#
# User 1 (Alice): sign the current plan and upload private ChatGPT messages.
# Run openbrain_plan_creation.sh first — the CLI state file remembers the plan_id.
#
# Env:
#   AUDITOR_TEE_URL   defaults to the Ben deployment
#   ALICE_KEY         defaults to ~/.auditor/keys/alice.json

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor
need python3

if [[ ! -f "$ALICE_KEY" ]]; then
  echo "missing key: $ALICE_KEY" >&2
  exit 1
fi

DATA_FILE="$(mktemp -t alice-conversations-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing Alice's ChatGPT messages"
cat > "$DATA_FILE" <<'JSON'
{
  "user": "participant-0ab3",
  "messages": [
    {"text": "Fix this bug: Traceback (most recent call last): File 'app.py', line 42, in <module> KeyError: 'user_id' — I'm hitting it when the session cookie is missing.", "prior": ""},
    {"text": "Rewrite this email to my manager so it sounds more professional and less passive: 'hey just checking in on the Q3 numbers whenever you get a sec'", "prior": ""},
    {"text": "What's the difference between correlation and causation? Use a short example.", "prior": ""},
    {"text": "Draft a thank-you note for my coworker who covered my shift last weekend. Warm but short.", "prior": ""},
    {"text": "Explain how a LEFT JOIN works in SQL and when you'd pick it over INNER JOIN.", "prior": ""},
    {"text": "Write a Dockerfile and a minimal docker-compose.yml for a FastAPI app that talks to Postgres.", "prior": ""},
    {"text": "How do I do my eyebrows if I've never plucked them before?", "prior": ""},
    {"text": "Can you write a short sci-fi story about a botanist stranded on Mars?", "prior": ""},
    {"text": "Recipe for weeknight chicken tikka masala, 45 minutes or less, with pantry substitutions for garam masala.", "prior": ""},
    {"text": "Summarize the causes of the French Revolution in three paragraphs for an 11th-grade history class.", "prior": ""},
    {"text": "Translate 'I'll be there in ten minutes, sorry for the delay' into Japanese, polite form.", "prior": ""},
    {"text": "What is 400000 divided by 23, and what is the square root of 144?", "prior": ""},
    {"text": "My wife is mad at me because I forgot our anniversary dinner reservation. How should I apologize?", "prior": ""},
    {"text": "Recommend a good laptop under $1000 for photo editing and light Lightroom work.", "prior": ""},
    {"text": "I'm feeling burned out at work and can't focus. What small things have helped other people?", "prior": ""},
    {"text": "Hi! How's it going today?", "prior": ""},
    {"text": "Draft slides for a 10-minute internal talk introducing our new incident response runbook.", "prior": ""},
    {"text": "Here's a spreadsheet with my expenses; tell me how much I spent on each category.", "prior": "User attached a 6-month personal expense export from their bank."},
    {"text": "What should my speech say for Karl at his retirement party? He was an electrician for 35 years.", "prior": ""},
    {"text": "Brainstorm names for a new coffee shop with a maritime theme.", "prior": ""}
  ]
}
JSON

log "Signing plan as user1 (Alice)"
auditor plan sign --user user1 --key "$ALICE_KEY"

log "Submitting Alice's messages"
auditor data submit --user user1 --key "$ALICE_KEY" --data "$DATA_FILE"

log "Done. Run ./sign_and_upload_user2.sh next."
