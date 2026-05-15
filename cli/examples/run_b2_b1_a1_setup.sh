#!/bin/bash
#
# Create and prepare the demo plans in the order used for the walkthrough:
#   1. B.2 Monitor Query Validation (failing demo)
#   2. B.1 Monitor Query Validation
#   3. A.1 Monitoring Policy + Query Executor + PII Policy Check
#
# For each plan, this script runs plan_creation.sh, then both users'
# sign_and_upload scripts. It does not execute the plans; use each example's
# execute.sh or the webapp after setup.
#
# Optional env inherited by the child scripts:
#   AUDITOR_TEE_URL   defaults inside each script to the Ben deployment
#   ALICE_KEY         defaults to ~/.auditor/keys/alice.json
#   OPENBRAIN_KEY     defaults to ~/.auditor/keys/openbrain.json
#   TINFOIL_API_KEY   used by A.1 plan_creation.sh when set

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }

run_example() {
  local example="$1"
  local dir="$SCRIPT_DIR/$example"

  if [[ ! -d "$dir" ]]; then
    echo "missing example directory: $dir" >&2
    exit 1
  fi

  log "$example: create plan"
  (cd "$dir" && ./plan_creation.sh)

  log "$example: sign/upload user1"
  (cd "$dir" && ./sign_and_upload_user1.sh)

  log "$example: sign/upload user2"
  (cd "$dir" && ./sign_and_upload_user2.sh)
}

run_example "B.2"
run_example "B.1"
run_example "A.1"

log "Done. B.2, B.1, and A.1 have been created and signed/uploaded."
echo "Run each plan from its example directory with ./execute.sh, or use the webapp."
