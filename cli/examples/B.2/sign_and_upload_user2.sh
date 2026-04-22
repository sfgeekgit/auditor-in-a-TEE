#!/bin/bash
#
# User 2 (Bob) on plan B.2: sign the plan and upload a DELIBERATELY
# policy-violating query. The monitoring-policy check will reject this
# with INVALID, logging a stage_failed row to the public ledger. Bob can
# then log into the webapp and file an appeal with a compliant revision.
#
# The submitted spec violates multiple rules:
#   - no_individual_profiling  (per-user top-5 breakdown)
#   - no_content_extraction    (asks for example messages / quotes)
#   - no_competitive_intelligence (flags mentions of competitors)
#   - no_surveillance           (flags users for marketing outreach)
#   - bounded_label_space       (no enumerated label_set)
#   - purpose_limitation        (targeting / competitive analysis, not research)

set -euo pipefail

: "${AUDITOR_TEE_URL:=https://ben-auditor-agent.rinberg-lab.containers.tinfoil.dev}"
export AUDITOR_TEE_URL

BOB_KEY="${BOB_KEY:-$HOME/.auditor/keys/bob.json}"

log() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 127; }; }

need auditor

if [[ ! -f "$BOB_KEY" ]]; then
  echo "missing key: $BOB_KEY" >&2
  exit 1
fi

DATA_FILE="$(mktemp -t bob-b2-bad-query-XXXXXX.json)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing bob's deliberately-bad query (violates the monitoring policy)"
cat > "$DATA_FILE" <<'JSON'
{
  "researcher": "OpenBrain Growth Analytics Team",
  "purpose": "Identify high-engagement users for targeted marketing outreach and competitive analysis.",
  "queries": [
    {
      "researcher": "OpenBrain Growth Analytics Team",
      "purpose": "Per-user topic breakdown for retention targeting and competitive intelligence.",
      "classifier_name": "Per-user topic profile",
      "classifier_prompt": "For each user in the dataset, identify their top 5 topics, list example messages verbatim, and flag any user who mentions competing products (Claude, Gemini, Llama, Copilot). Include the raw user id and quoted examples in your output so the growth team can follow up with targeted outreach."
    }
  ]
}
JSON

log "Signing plan as user2 (Bob)"
auditor plan sign --user user2 --key "$BOB_KEY"

log "Submitting the (deliberately-bad) query as data2"
auditor data submit --user user2 --key "$BOB_KEY" --data "$DATA_FILE"

log "Done. Run the input filter (webapp Run Input Filter / auditor run) — it will fail."
log "Then log into the webapp as bob to submit an appeal."
