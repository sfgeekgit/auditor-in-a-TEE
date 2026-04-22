#!/bin/bash
#
# Plan B.2 — creation.
#
# Demonstrates the appeals flow: the plan mirrors B.1, but user 2 (bob)
# submits a query that deliberately violates the monitoring policy. The
# input-stage check emits INVALID, the public ledger records the
# failure, and bob can appeal from his logged-in view in the webapp —
# submitting a revised query that (if accepted) triggers an LLM diff
# summary posted to the ledger.
#
# Next:
#   ./sign_and_upload_user1.sh     (placeholder for alice)
#   ./sign_and_upload_user2.sh     (bob's deliberately-bad query)
#   then run the plan (webapp "Run Input Filter" or `auditor run`);
#   the input stage will fail — switch to bob's login to appeal.

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

PLAN_FILE="$(mktemp -t plan-B2-XXXXXX.yaml)"
trap 'rm -f "$PLAN_FILE"' EXIT

log "Writing plan B.2: Monitor Query Validation (failing demo)"
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
  ./sign_and_upload_user1.sh    (alice placeholder)
  ./sign_and_upload_user2.sh    (bob's deliberately-bad query)
  then in the webapp: hit "Run Input Filter" — expect a failure.
  Log in as bob to appeal with a compliant revised query.
MSG
