#!/bin/bash
#
# Step 1 of the OpenAI ChatGPT Usage Audit demo.
#
# Builds a three-step plan:
#   step 0 — Monitoring Policy Check: audits the researcher's spec
#            (data2) against a published policy on acceptable analysis.
#            Rejects competitive intelligence, per-user profiling,
#            surveillance, and content extraction. Emits VALID/INVALID.
#   step 1 — Classifiers: runs Appendix A §A.1/§A.2/§A.3 from
#            "How People Use ChatGPT" over the user's messages, emits
#            Markdown aggregate report with k-anonymity applied.
#   step 2 — Privacy Sentinel: audits the classifier output for any
#            leak of raw content, PII, small buckets, or identifiers.
#            Emits VALID/INVALID.
#
# The webapp withholds all step output and shows only the error when
# any sentinel node emits INVALID.
#
# Next:
#   ./sign_and_upload_user1.sh
#   ./sign_and_upload_user2.sh
#   ./execute.sh            (or click "Run Computation" in the webapp)
#
# Env:
#   AUDITOR_TEE_URL   defaults to the Ben deployment
#   ALICE_KEY         defaults to ~/.auditor/keys/alice.json
#   OPENAI_KEY        defaults to ~/.auditor/keys/openai.json
#   TINFOIL_API_KEY   optional; patched into plan.yaml if set

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"
OPENAI_KEY="${OPENAI_KEY:-$HOME/.auditor/keys/openai.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor
need python3
need curl

for f in "$ALICE_KEY" "$OPENAI_KEY"; do
  if [[ ! -f "$f" ]]; then
    echo "missing key file: $f" >&2
    echo "generate once with:  auditor keygen --out $f" >&2
    exit 1
  fi
done

log "Probing $AUDITOR_TEE_URL/health"
curl -sS --fail "$AUDITOR_TEE_URL/health" && echo

ALICE_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$ALICE_KEY")
OAI_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$OPENAI_KEY")
echo "  alice  pk: $ALICE_PK"
echo "  openai pk: $OAI_PK"

PLAN_FILE="$(mktemp -t openai-plan-XXXXXX.yaml)"
trap 'rm -f "$PLAN_FILE"' EXIT

log "Writing plan: Appendix A classifiers + privacy sentinel"
cp "$SCRIPT_DIR/plan.yaml" "$PLAN_FILE"

python3 - "$ALICE_PK" "$OAI_PK" "$PLAN_FILE" "${TINFOIL_API_KEY:-}" <<'PY'
import pathlib, re, sys
alice_pk, oai_pk, path, api_key = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace("__ALICE_PK__", alice_pk).replace("__OPENAI_PK__", oai_pk)
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
