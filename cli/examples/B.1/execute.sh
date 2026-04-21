#!/bin/bash
#
# Execute the current plan inside the TEE and dump results. Requires that
# both users have already signed and submitted data (plan status must be
# data_ready). The webapp's "Run Computation" button does the same thing.
#
# Env:
#   AUDITOR_TEE_URL   defaults to the Ben deployment
#   RESULTS_FILE      where to write full JSON results (default: ./results.json)

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL
RESULTS_FILE="${RESULTS_FILE:-results.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor
need python3

log "Running computation inside the TEE"
auditor run

log "Fetching final results → $RESULTS_FILE"
auditor results --json > "$RESULTS_FILE"

python3 - "$RESULTS_FILE" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print(f"plan status: {r['status']}")
print(f"steps:       {len(r['results'])}")
for s in r['results']:
    kind = s.get('type', '?')
    status = s.get('status', '?')
    length = len(str(s.get('result', '')))
    print(f"  step {s['step']:>2} {kind:<10} {status:<8} ({length} chars)")
PY
