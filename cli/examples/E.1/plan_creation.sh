#!/bin/bash
#
# Plan E.1 — creation.
#
# Redacted personal emails + narrow topic query. user1 (alice) uploads
# emails with sensitive spans in [[REDACTED: … ]] tags. user2 (bob) asks
# a narrow yes/no topic-presence question. The TEE answers with a single
# YES or NO and the redaction sentinel blocks anything else.
#
# Steps:
#   step 0 — Topic Question Check   (input, VALID/INVALID)
#   step 1 — Redaction Topic Probe  (query, emits YES or NO)
#   step 2 — Leak Check             (output, VALID/INVALID)
#
# Next:
#   ./sign_and_upload_user1.sh    (uploads the redacted emails)
#   ./sign_and_upload_user2.sh    (uploads bob's question)
#   ./execute.sh                   (or Run All in the webapp)

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
echo "  alice pk: $ALICE_PK"
echo "  bob   pk: $BOB_PK"

PLAN_FILE="$(mktemp -t plan-E1-XXXXXX.yaml)"
trap 'rm -f "$PLAN_FILE"' EXIT

log "Writing plan E.1: Email Topic Check (redacted emails)"
cp "$SCRIPT_DIR/plan.yaml" "$PLAN_FILE"

python3 - "$ALICE_PK" "$BOB_PK" "$PLAN_FILE" <<'PY'
import pathlib, sys
alice_pk, bob_pk, path = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace("__ALICE_PK__", alice_pk).replace("__BOB_PK__", bob_pk)
p.write_text(text)
PY

log "Creating plan on the TEE"
auditor plan create "$PLAN_FILE"

log "Plan created. Summary:"
auditor plan show

cat <<MSG

Next steps:
  ./sign_and_upload_user1.sh   (redacted emails)
  ./sign_and_upload_user2.sh   (bob's question)
  ./execute.sh                  (or Run All in the webapp)
MSG
