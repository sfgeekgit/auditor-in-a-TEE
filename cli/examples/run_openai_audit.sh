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

log "1. Generating keypairs"
mkdir -p keys
auditor keygen --out "$WORKDIR/keys/alice.json"
auditor keygen --out "$WORKDIR/keys/openai.json"

ALICE_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$WORKDIR/keys/alice.json")
OAI_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$WORKDIR/keys/openai.json")
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
auditor plan sign --user user1 --key "$WORKDIR/keys/alice.json"
auditor plan sign --user user2 --key "$WORKDIR/keys/openai.json"

log "6. Writing sample private data"
cat > alice-conversations.json <<'JSON'
[
  {"id":"c1","timestamp":"2024-03-11","context":"work","messages":[{"role":"user","content":"Debug this Python IndexError"},{"role":"assistant","content":"..."}]},
  {"id":"c2","timestamp":"2024-03-11","context":"personal","messages":[{"role":"user","content":"Write a poem about the ocean"},{"role":"assistant","content":"..."}]},
  {"id":"c3","timestamp":"2024-03-12","context":"work","messages":[{"role":"user","content":"Explain SQL JOIN types"},{"role":"assistant","content":"..."},{"role":"user","content":"What about FULL OUTER?"},{"role":"assistant","content":"..."}]},
  {"id":"c4","timestamp":"2024-03-12","context":"work","messages":[{"role":"user","content":"Draft an email to my manager"},{"role":"assistant","content":"..."}]},
  {"id":"c5","timestamp":"2024-03-13","context":"personal","messages":[{"role":"user","content":"Probability of rolling a 6 with three dice?"},{"role":"assistant","content":"..."},{"role":"user","content":"Show the formula"},{"role":"assistant","content":"..."}]},
  {"id":"c6","timestamp":"2024-03-13","context":"work","messages":[{"role":"user","content":"Review this React component for re-renders"},{"role":"assistant","content":"..."}]},
  {"id":"c7","timestamp":"2024-03-14","context":"personal","messages":[{"role":"user","content":"Short sci-fi story about Mars"},{"role":"assistant","content":"..."}]},
  {"id":"c8","timestamp":"2024-03-14","context":"work","messages":[{"role":"user","content":"Analyze these sales numbers"},{"role":"assistant","content":"..."},{"role":"user","content":"Summary table please"},{"role":"assistant","content":"..."}]},
  {"id":"c9","timestamp":"2024-03-15","context":"work","messages":[{"role":"user","content":"Fix a CORS error in FastAPI"},{"role":"assistant","content":"..."}]},
  {"id":"c10","timestamp":"2024-03-15","context":"personal","messages":[{"role":"user","content":"Should I learn Rust or Go?"},{"role":"assistant","content":"..."}]}
]
JSON

cat > openai-queries.json <<'JSON'
{
  "researcher": "OpenAI Research Team",
  "queries": [
    {"id":"q1","question":"What percentage of conversations are work vs personal?","type":"work_personal_split"},
    {"id":"q2","question":"Distribution of use-case categories?","type":"use_case_distribution"},
    {"id":"q3","question":"Average turns per conversation by category?","type":"multi_turn_analysis"}
  ]
}
JSON

log "7. Both parties submit data"
auditor data submit --user user1 --key "$WORKDIR/keys/alice.json" --data alice-conversations.json
auditor data submit --user user2 --key "$WORKDIR/keys/openai.json" --data openai-queries.json

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
