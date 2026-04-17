#!/bin/bash
#
# Full salary-benchmarking example end-to-end.
#
# Two companies compare compensation bands without revealing individual salaries.
# One run_python step computes percentiles; one run_llm step checks compliance
# with the "no individual salaries" / "suppress groups <3" rules.
#
# Usage:
#   AUDITOR_TEE_URL=http://127.0.0.1:8088 ./run_salary.sh          # local
#   AUDITOR_TEE_URL=https://<enclave>.tinfoil.dev ./run_salary.sh  # deployed
#
# Optional env:
#   TINFOIL_API_KEY     real API key for the run_llm step (local dev only —
#                       on a deployed enclave the container env has it)
#   WORKDIR             working dir (default: mktemp)
#   KEEP                set to 1 to keep WORKDIR after the run

set -euo pipefail

: "${AUDITOR_TEE_URL:?set AUDITOR_TEE_URL to the TEE server (e.g. http://127.0.0.1:8088)}"
export AUDITOR_TEE_URL

WORKDIR="${WORKDIR:-$(mktemp -d -t auditor-salary-XXXXXX)}"
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
auditor keygen --out "$WORKDIR/keys/acme.json"
auditor keygen --out "$WORKDIR/keys/globex.json"

ACME_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$WORKDIR/keys/acme.json")
GLOBEX_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$WORKDIR/keys/globex.json")
echo "  acme   pk: $ACME_PK"
echo "  globex pk: $GLOBEX_PK"

log "2. Writing plan from the salary template"
auditor plan template salary --out plan.yaml

# Patch in the real pubkeys (and an optional Tinfoil API key for local dev).
python3 - "$ACME_PK" "$GLOBEX_PK" "${TINFOIL_API_KEY:-}" <<'PY'
import pathlib, re, sys
acme_pk, globex_pk, api_key = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path("plan.yaml")
text = p.read_text()
text = text.replace("deadbeef" * 8, acme_pk).replace("cafebabe" * 8, globex_pk)
if api_key:
    text = re.sub(r"^tinfoil_api_key:.*$", f'tinfoil_api_key: "{api_key}"', text, flags=re.MULTILINE)
p.write_text(text)
PY

log "3. Creating plan on the TEE"
auditor plan create plan.yaml

log "4. Reviewing"
auditor plan show

log "5. Both parties sign"
auditor plan sign --user user1 --key "$WORKDIR/keys/acme.json"
auditor plan sign --user user2 --key "$WORKDIR/keys/globex.json"

log "6. Writing sample private data"
cat > acme.json <<'JSON'
{
  "company": "Acme Corp",
  "employees": [
    {"role": "Software Engineer",        "department": "Engineering", "annual_comp": 145000},
    {"role": "Senior Software Engineer", "department": "Engineering", "annual_comp": 185000},
    {"role": "Software Engineer",        "department": "Engineering", "annual_comp": 152000},
    {"role": "Staff Engineer",           "department": "Engineering", "annual_comp": 210000},
    {"role": "Engineering Manager",      "department": "Engineering", "annual_comp": 195000},
    {"role": "Product Manager",          "department": "Product",     "annual_comp": 160000},
    {"role": "Senior Product Manager",   "department": "Product",     "annual_comp": 185000},
    {"role": "Product Manager",          "department": "Product",     "annual_comp": 155000},
    {"role": "Designer",                 "department": "Design",      "annual_comp": 130000},
    {"role": "Senior Designer",          "department": "Design",      "annual_comp": 158000},
    {"role": "Designer",                 "department": "Design",      "annual_comp": 135000},
    {"role": "Sales Rep",                "department": "Sales",       "annual_comp": 120000},
    {"role": "Senior Sales Rep",         "department": "Sales",       "annual_comp": 145000},
    {"role": "Sales Rep",                "department": "Sales",       "annual_comp": 125000},
    {"role": "Sales Manager",            "department": "Sales",       "annual_comp": 165000},
    {"role": "General Counsel",          "department": "Legal",       "annual_comp": 195000},
    {"role": "Contract Attorney",        "department": "Legal",       "annual_comp": 155000},
    {"role": "HR Manager",               "department": "HR",          "annual_comp": 125000}
  ]
}
JSON

cat > globex.json <<'JSON'
{
  "company": "Globex Inc",
  "employees": [
    {"role": "Software Engineer",        "department": "Engineering", "annual_comp": 155000},
    {"role": "Senior Software Engineer", "department": "Engineering", "annual_comp": 195000},
    {"role": "Software Engineer",        "department": "Engineering", "annual_comp": 160000},
    {"role": "Staff Engineer",           "department": "Engineering", "annual_comp": 225000},
    {"role": "Software Engineer",        "department": "Engineering", "annual_comp": 150000},
    {"role": "Engineering Manager",      "department": "Engineering", "annual_comp": 205000},
    {"role": "Product Manager",          "department": "Product",     "annual_comp": 170000},
    {"role": "Senior Product Manager",   "department": "Product",     "annual_comp": 195000},
    {"role": "Product Manager",          "department": "Product",     "annual_comp": 165000},
    {"role": "Designer",                 "department": "Design",      "annual_comp": 140000},
    {"role": "Senior Designer",          "department": "Design",      "annual_comp": 165000},
    {"role": "Designer",                 "department": "Design",      "annual_comp": 142000},
    {"role": "Sales Rep",                "department": "Sales",       "annual_comp": 115000},
    {"role": "Senior Sales Rep",         "department": "Sales",       "annual_comp": 140000},
    {"role": "Sales Rep",                "department": "Sales",       "annual_comp": 118000},
    {"role": "Corporate Counsel",        "department": "Legal",       "annual_comp": 185000},
    {"role": "HR Director",              "department": "HR",          "annual_comp": 145000},
    {"role": "HR Coordinator",           "department": "HR",          "annual_comp": 95000}
  ]
}
JSON

log "7. Both parties submit data"
auditor data submit --user user1 --key "$WORKDIR/keys/acme.json"   --data acme.json
auditor data submit --user user2 --key "$WORKDIR/keys/globex.json" --data globex.json

log "8. Running computation inside the TEE"
auditor run

log "9. Fetching final results"
auditor results --json > results.json
echo "results written to $WORKDIR/results.json"
echo
python3 -c "
import json
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
