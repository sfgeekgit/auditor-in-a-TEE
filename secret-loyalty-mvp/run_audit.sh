#!/bin/bash
# Part 2: create plan.yaml on the auditor box, sign + upload as lab (user1) and
# auditor (user2), run the three stages, and save results + ledger here.
#
#   ./run_audit.sh                      # run as cc; uses sudo to act as the `auditor` user
#   PLAN=plan_v1.json ./run_audit.sh    # a different plan file (default plan.yaml)
#   DATA=train_p0_c100.jsonl ./run_audit.sh   # a different dataset (default train.jsonl)
#
# Stages are run one at a time with curl rather than `auditor run`, because the
# CLI's HTTP timeout is 60 s and the query step reads the whole dataset.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR=/home/auditor/secret-loyalty-run
URL=http://localhost:8080
PLAN="${PLAN:-plan.yaml}"
DATA="${DATA:-train.jsonl}"
KEYS=/home/auditor/.auditor/keys

sudo install -d -o auditor -g auditor "$RUN_DIR"
sudo install -o auditor -g auditor -m 0644 "$HERE"/{"$PLAN","$DATA",question.txt} "$RUN_DIR"/

sudo -u auditor env URL="$URL" KEYS="$KEYS" PLAN="$PLAN" DATA="$DATA" bash -euo pipefail -c '
cd '"$RUN_DIR"'
export PATH=/home/auditor/auditor-in-a-TEE/.venv/bin:$PATH AUDITOR_TEE_URL=$URL
rm -rf .auditor
auditor plan create $PLAN
auditor plan sign   --user user1 --key $KEYS/lab.json
auditor data submit --user user1 --key $KEYS/lab.json --data $DATA
auditor plan sign   --user user2 --key $KEYS/auditor.json
auditor data submit --user user2 --key $KEYS/auditor.json --data question.txt
PLANFILE=$PLAN
PLAN=$(python3 -c "import json; print(json.load(open(\".auditor/state.json\"))[\"plan_id\"])")
echo "plan id: $PLAN"
# Publish the source file so the web UI can link to it ("View plan YAML").
case $PLANFILE in *.yaml|*.yml) install -D -m 0644 $PLANFILE /home/auditor/auditor-in-a-TEE-webapp/yaml/$PLAN.yaml ;; esac
for stage in input query output; do
  echo "== $stage"
  curl -sS --max-time 900 -X POST "$URL/plan/$PLAN/run-stage" \
       -H "Content-Type: application/json" -d "{\"stage\": \"$stage\"}" \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print(r.get(\"stage_status\"), r.get(\"overall_status\"), r.get(\"detail\", \"\"))"
done
curl -sS "$URL/plan/$PLAN/results" > results.json
curl -sS "$URL/plan/$PLAN/ledger"  > ledger.json
'
sudo cp "$RUN_DIR"/results.json "$RUN_DIR"/ledger.json "$HERE"/
sudo chown "$(id -un)": "$HERE"/results.json "$HERE"/ledger.json
python3 - "$HERE/results.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print("status:", r["status"], r["stage_status"])
out = (r["stage_results"].get("output") or [{}])[-1].get("result")
print("released output:\n", out)
PY
