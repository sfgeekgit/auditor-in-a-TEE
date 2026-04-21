#!/bin/bash
#
# Plan A.1 — creation.
#
# Uploads the generic three-step plan (Monitoring Policy + Query
# Executor + PII Policy Check) with name "A.1". The classifier prompt
# itself is NOT in this plan — it lives in user2's submitted data, so
# user1 can sign the plan without seeing the specific prompt text. For
# this plan, user2 will submit Appendix A.1 (Work / Non-Work) verbatim
# from "How People Use ChatGPT" (Chatterji et al., 2025).
#
# Steps in the plan:
#   step 0 — Monitoring Policy Check (audits the submitted prompt)
#   step 1 — Query Executor (runs the submitted prompt on user1 data)
#   step 2 — PII Policy Check (audits step 1 output)
#
# Next:
#   ./sign_and_upload_user1.sh
#   ./sign_and_upload_user2.sh
#   ./execute.sh            (or click "Run Computation" in the webapp)
#
# Env:
#   AUDITOR_TEE_URL   defaults to the Ben deployment
#   ALICE_KEY         defaults to ~/.auditor/keys/alice.json
#   OPENBRAIN_KEY        defaults to ~/.auditor/keys/openbrain.json
#   TINFOIL_API_KEY   optional; patched into plan.yaml if set

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"
OPENBRAIN_KEY="${OPENBRAIN_KEY:-$HOME/.auditor/keys/openbrain.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor
need python3
need curl

for f in "$ALICE_KEY" "$OPENBRAIN_KEY"; do
  if [[ ! -f "$f" ]]; then
    echo "missing key file: $f" >&2
    echo "generate once with:  auditor keygen --out $f" >&2
    exit 1
  fi
done

log "Probing $AUDITOR_TEE_URL/health"
curl -sS --fail "$AUDITOR_TEE_URL/health" && echo

ALICE_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$ALICE_KEY")
OAI_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$OPENBRAIN_KEY")
echo "  alice  pk: $ALICE_PK"
echo "  openbrain pk: $OAI_PK"

PLAN_FILE="$(mktemp -t plan-A1-XXXXXX.yaml)"
trap 'rm -f "$PLAN_FILE"' EXIT

log "Writing plan A.1: Monitoring Policy + Query Executor + PII Policy Check"
cp "$SCRIPT_DIR/plan.yaml" "$PLAN_FILE"

python3 - "$ALICE_PK" "$OAI_PK" "$PLAN_FILE" "${TINFOIL_API_KEY:-}" <<'PY'
import pathlib, re, sys
alice_pk, oai_pk, path, api_key = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace("__ALICE_PK__", alice_pk).replace("__OPENBRAIN_PK__", oai_pk)
if api_key:
    text = re.sub(r"^tinfoil_api_key:.*$", f'tinfoil_api_key: "{api_key}"', text, flags=re.MULTILINE)
p.write_text(text)
PY

log "Creating plan on the TEE"
auditor plan create "$PLAN_FILE"

log "Plan created. Summary:"
auditor plan show

cat <<MSG

Next steps:
  ./sign_and_upload_user1.sh
  ./sign_and_upload_user2.sh
  ./execute.sh         (or click "Run Computation" in the webapp)
MSG
