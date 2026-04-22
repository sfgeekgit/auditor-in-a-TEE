#!/bin/bash
#
# User 1 (Alice, the accountant) on plan D.1: sign the plan and upload
# three months of the small business's bank statements with sensitive
# identifiers masked as [[REDACTED:kind_id]]. The raw data would contain
# vendor names, customer names, and per-employee payroll — none of that
# leaves the accountant's side.
#
# Run plan_creation.sh first — the CLI state file remembers the plan_id.

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

ALICE_KEY="${ALICE_KEY:-$HOME/.auditor/keys/alice.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor

if [[ ! -f "$ALICE_KEY" ]]; then
  echo "missing key: $ALICE_KEY" >&2
  exit 1
fi

DATA_FILE="$(mktemp -t alice-d1-statements-XXXXXX.txt)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing redacted bank statements (Jan–Mar 2025)"
cat > "$DATA_FILE" <<'TXT'
Bank Statement — Jan 2025
Account: [[REDACTED:account]]

01/05  Deposit  [[REDACTED:customer_A]]   $10,000.00
01/07  Deposit  [[REDACTED:customer_B]]   $8,300.00
01/10  Payroll  [[REDACTED:employee_1]]   -$4,200.00
01/12  Payment  [[REDACTED:vendor_X]]     -$2,800.00
01/15  Deposit  [[REDACTED:customer_A]]   $2,500.00
01/18  Deposit  [[REDACTED:customer_C]]   $6,500.00
01/20  Payroll  [[REDACTED:employee_2]]   -$3,800.00
01/22  Deposit  [[REDACTED:customer_D]]   $5,200.00
01/25  Payment  [[REDACTED:vendor_Y]]     -$1,400.00
01/28  Deposit  [[REDACTED:customer_E]]   $4,200.00

Bank Statement — Feb 2025
Account: [[REDACTED:account]]

02/03  Deposit  [[REDACTED:customer_A]]   $9,000.00
02/06  Payroll  [[REDACTED:employee_1]]   -$4,200.00
02/08  Deposit  [[REDACTED:customer_B]]   $8,500.00
02/11  Payment  [[REDACTED:vendor_X]]     -$2,600.00
02/14  Deposit  [[REDACTED:customer_C]]   $7,200.00
02/17  Payroll  [[REDACTED:employee_2]]   -$3,800.00
02/20  Deposit  [[REDACTED:customer_D]]   $4,800.00
02/24  Payment  [[REDACTED:vendor_Z]]     -$950.00
02/27  Deposit  [[REDACTED:customer_E]]   $3,200.00

Bank Statement — Mar 2025
Account: [[REDACTED:account]]

03/02  Deposit  [[REDACTED:customer_A]]   $16,000.00
03/05  Payroll  [[REDACTED:employee_1]]   -$4,200.00
03/09  Payment  [[REDACTED:vendor_X]]     -$3,100.00
03/12  Deposit  [[REDACTED:customer_B]]   $6,000.00
03/15  Payroll  [[REDACTED:employee_2]]   -$3,800.00
03/19  Deposit  [[REDACTED:customer_C]]   $5,000.00
03/22  Deposit  [[REDACTED:customer_A]]   $2,500.00
03/26  Payment  [[REDACTED:vendor_Y]]     -$1,200.00
03/29  Deposit  [[REDACTED:customer_D]]   $3,500.00
TXT

log "Signing plan as user1 (Alice, the accountant)"
auditor plan sign --user user1 --key "$ALICE_KEY"

log "Submitting redacted bank statements"
auditor data submit --user user1 --key "$ALICE_KEY" --data "$DATA_FILE"

log "Done. Plan still needs the lender (user2) to sign + submit."
