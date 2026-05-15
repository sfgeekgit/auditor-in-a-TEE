#!/bin/bash
#
# Plan B.1 — creation.
#
# Filter-only plan: audits researcher specs against the published monitoring
# policy, then runs an output filter that releases only VALID / INVALID.
#
# Next:
#   ./sign_and_upload_user1.sh   (uploads the A.1-style spec as user1)
#   ./sign_and_upload_user2.sh   (uploads the A.2-style spec as user2)
#   ./execute.sh                  (or click Run All in the webapp)
#
# Env:
#   AUDITOR_TEE_URL   defaults to the Ben deployment
#   ALICE_KEY         defaults to ~/.auditor/keys/alice.json
#   OPENBRAIN_KEY     defaults to ~/.auditor/keys/openbrain.json

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
OB_PK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['public_key'])" "$OPENBRAIN_KEY")
echo "  alice     pk: $ALICE_PK"
echo "  openbrain pk: $OB_PK"

PLAN_FILE="$(mktemp -t plan-B1-XXXXXX.yaml)"
trap 'rm -f "$PLAN_FILE"' EXIT

log "Writing plan B.1: Query Validation (two researcher specs)"
cp "$SCRIPT_DIR/plan.yaml" "$PLAN_FILE"

python3 - "$ALICE_PK" "$OB_PK" "$PLAN_FILE" <<'PY'
import pathlib, sys
alice_pk, ob_pk, path = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace("__ALICE_PK__", alice_pk).replace("__OPENBRAIN_PK__", ob_pk)
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
  ./execute.sh          (or click Run All in the webapp)
MSG
