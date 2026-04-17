#!/bin/bash
#
# Full openai_audit example end-to-end.
#
# Usage:
#   # Against a local dev server:
#   (cd ../webapp && REQUIRE_SIGNATURES=true python3 -m uvicorn api_server:app --port 8088) &
#   AUDITOR_TEE_URL=http://127.0.0.1:8088 ./run_openai_audit.sh
#
#   # Against a deployed Tinfoil enclave:
#   tinfoil attestation verify -e my-enclave.tinfoil.dev -r RoyRin/auditor-in-a-TEE-deployer
#   AUDITOR_TEE_URL=https://my-enclave.tinfoil.dev ./run_openai_audit.sh
#
# Optional env:
#   TINFOIL_API_KEY     real API key for the LLM steps (otherwise prompts render but
#                       are not sent to a model)
#   WORKDIR             working dir (default: mktemp)
#   KEEP                set to 1 to keep WORKDIR after the run

set -euo pipefail

: "${AUDITOR_TEE_URL:?set AUDITOR_TEE_URL to the TEE server (e.g. http://127.0.0.1:8088)}"
export AUDITOR_TEE_URL

WORKDIR="${WORKDIR:-$(mktemp -d -t auditor-openai-XXXXXX)}"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

cleanup() {
  if [[ "${KEEP:-0}" != "1" ]]; then
    rm -rf "$WORKDIR"
  else
    echo "WORKDIR kept at $WORKDIR"
  fi
}
trap cleanup EXIT

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor
need python3
need curl

log "0. Probing $AUDITOR_TEE_URL/health"
curl -sS --fail "$AUDITOR_TEE_URL/health" && echo

log "1. Using existing keypairs"
ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"
OPENAI_KEY="${OPENAI_KEY:-$HOME/.auditor/keys/openai.json}"

for f in "$ALICE_KEY" "$OPENAI_KEY"; do
  if [[ ! -f "$f" ]]; then
    echo "missing key file: $f" >&2
    echo "generate once with:  auditor keygen --out $f" >&2
    exit 1
  fi
done

ALICE_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$ALICE_KEY")
OAI_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$OPENAI_KEY")
echo "  alice  pk: $ALICE_PK"
echo "  openai pk: $OAI_PK"

log "2. Writing plan from the openai_audit template"
auditor plan template openai_audit --out plan.yaml

# Patch in the real pubkeys (and an optional Tinfoil API key).
python3 - "$ALICE_PK" "$OAI_PK" "${TINFOIL_API_KEY:-}" <<'PY'
import pathlib, re, sys
alice_pk, oai_pk, api_key = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path("plan.yaml")
text = p.read_text()
text = text.replace("deadbeef" * 8, alice_pk).replace("cafebabe" * 8, oai_pk)
if api_key:
    text = re.sub(r"^tinfoil_api_key:.*$", f'tinfoil_api_key: "{api_key}"', text, flags=re.MULTILINE)
p.write_text(text)
PY

log "3. Creating plan on the TEE"
auditor plan create plan.yaml

log "4. Reviewing"
auditor plan show

log "5. Both parties sign"
auditor plan sign --user user1 --key "$ALICE_KEY"
auditor plan sign --user user2 --key "$OPENAI_KEY"

log "6. Writing sample private data"
cat > alice-conversations.json <<'JSON'
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

cat > openai-queries.json <<'JSON'
{
  "researcher": "OpenAI Economic Research",
  "classifiers": [
    "work_nonwork",
    "asking_doing_expressing",
    "conversation_topic"
  ]
}
JSON

log "7. Both parties submit data"
auditor data submit --user user1 --key "$ALICE_KEY" --data alice-conversations.json
auditor data submit --user user2 --key "$OPENAI_KEY" --data openai-queries.json

log "8. Running computation inside the TEE"
auditor run

log "9. Fetching final results"
auditor results --json > results.json
echo "results written to $WORKDIR/results.json"
echo
python3 -c "
import json,sys
r = json.load(open('results.json'))
print(f\"plan status: {r['status']}\")
print(f\"steps:       {len(r['results'])}\")
for s in r['results']:
    kind = s.get('type', '?')
    status = s.get('status', '?')
    length = len(str(s.get('result','')))
    print(f\"  step {s['step']:>2} {kind:<10} {status:<8} ({length} chars)\")
"

log "Done."
