#!/bin/bash
#
# Plan D.1 — creation.
#
# Redacted-statements loan underwriting. User 1 (accountant) uploads bank
# statements with sensitive identifiers masked as [[REDACTED:…]] tags.
# The underwriting rule — "no single counterparty > 40% of monthly
# revenue" — is agreed via the plan itself, so user 2 (lender bob) is a
# co-signer only and uploads just a placeholder.
#
# Steps in the plan:
#   step 0 — Extract Data                (query, LLM, emits JSON)
#   step 1 — Concentration Verdict        (output, python, emits VALID/INVALID)
#
# Next:
#   ./sign_and_upload_user1.sh   (uploads the redacted statements)
#   ./sign_and_upload_user2.sh   (co-sign + placeholder upload for bob)
#   ./execute.sh                  (or Run All in the webapp)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"
BOB_KEY="${BOB_KEY:-$HOME/.auditor/keys/bob.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor
need python3
need curl

for f in "$ALICE_KEY" "$BOB_KEY"; do
  if [[ ! -f "$f" ]]; then
    echo "missing key file: $f" >&2
    echo "generate once with:  auditor keygen --out $f" >&2
    exit 1
  fi
done

log "Probing $AUDITOR_TEE_URL/health"
curl -sS --fail "$AUDITOR_TEE_URL/health" && echo

ALICE_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$ALICE_KEY")
BOB_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$BOB_KEY")
echo "  alice     pk: $ALICE_PK"
echo "  bob       pk: $BOB_PK"

PLAN_FILE="$(mktemp -t plan-D1-XXXXXX.yaml)"
trap 'rm -f "$PLAN_FILE"' EXIT

log "Writing plan D.1: Loan Underwriting (redacted statements)"
cp "$SCRIPT_DIR/plan.yaml" "$PLAN_FILE"

python3 - "$ALICE_PK" "$BOB_PK" "$PLAN_FILE" <<'PY'
import pathlib, sys
alice_pk, ob_pk, path = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace("__ALICE_PK__", alice_pk).replace("__BOB_PK__", ob_pk)
p.write_text(text)
PY

log "Creating plan on the TEE"
auditor plan create "$PLAN_FILE"

log "Plan created. Summary:"
auditor plan show

cat <<MSG

Next steps:
  ./sign_and_upload_user1.sh    (redacted bank statements)
  ./sign_and_upload_user2.sh    (underwriting rule)
  ./execute.sh                   (or Run All in the webapp)
MSG
