#!/bin/bash
#
# User 1 (Alice) on plan E.1: sign and upload a batch of personal emails
# where sensitive spans are wrapped in [[REDACTED: … ]] tags. The content
# inside the tags is what Alice considers private — the TEE is allowed
# to inspect it to answer bob's narrow question, but must never surface
# any of it.

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

DATA_FILE="$(mktemp -t alice-e1-emails-XXXXXX.txt)"
trap 'rm -f "$DATA_FILE"' EXIT

log "Writing alice's redacted email corpus"
cat > "$DATA_FILE" <<'TXT'
From: sam@friendmail.example
To: alice@example.com
Date: 2025-03-10
Subject: dinner friday?

Hey Alice,

[[REDACTED: Are you free Friday evening? I was thinking that new Italian place on Main Street — the one with the rooftop. Let me know if 7pm works for you.]]

Hope you're well!
—Sam

---

From: mom@family.example
To: alice@example.com
Date: 2025-03-12
Subject: update from home

Alice,

Just wanted to pass along some news. [[REDACTED: Dad's surgery went well yesterday — they removed the polyps and everything looked clean. He's recovering at the Northside rehab center and should be home by the weekend. The doctor said follow-up in six months.]]

Call when you have a minute.

Love,
Mom

---

From: alerts@brokerage.example
To: alice@example.com
Date: 2025-03-15
Subject: Order filled

[[REDACTED: Your market order to buy 250 shares of NVDA has been executed at $495.32 per share, totaling $123,830.00 including the $12.50 fee. Trade reference #TRX-9481-2025. Your account balance will update overnight. Position now: 820 shares NVDA, 140 shares MSFT, 60 shares JPM.]]

This is an automated notification. Do not reply.

---

From: manager@work.example
To: alice@example.com
Date: 2025-03-18
Subject: Q1 review

Alice,

[[REDACTED: Can you review the Q1 numbers in the shared deck (link in the team channel) and send me your comments by Friday EOB? Focus especially on the sales-by-region slide — I think the Southwest numbers look off.]]

Thanks,
Priya

---

From: news@morningbrief.example
To: alice@example.com
Date: 2025-03-20
Subject: today's briefing

Good morning. Today's briefing: markets opened mixed; tech is modestly up, energy down. Weather: mild and sunny across most of the country. Top story: the new federal infrastructure bill passed committee overnight.

(No redactions in this newsletter — included to show that not every email has private spans.)

---

From: gym@local.example
To: alice@example.com
Date: 2025-03-22
Subject: class reminder

Hey Alice, [[REDACTED: this is a reminder that your yoga class is this Sunday at 9am with instructor Mara. Please bring a mat and water bottle.]]

See you there!
TXT

log "Signing plan as user1 (Alice)"
auditor plan sign --user user1 --key "$ALICE_KEY"

log "Submitting redacted email corpus"
auditor data submit --user user1 --key "$ALICE_KEY" --data "$DATA_FILE"

log "Done. Plan still needs Bob (user2) to sign + submit his question."
