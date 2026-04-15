# `auditor` CLI

Command-line client for the [auditor-in-a-TEE](..) multi-party computation service.

Two parties with private data agree on a computation plan, sign it with ed25519 keys, submit their data to a Trusted Execution Environment, and receive results. Neither party ever sees the other's raw data — only the outputs the plan explicitly produces.

## How it works

```
   Party A                    TEE (public + attestable)                  Party B
     │                                 │                                    │
     │   1. write plan.yaml            │                                    │
     │──► create ─── POST /plan ──────►│                                    │
     │◄──── plan_id + plan_hash ───────│                                    │
     │                                 │                                    │
     │   2. review (sign)              │                                    │
     │──► sign ───── POST /sign ──────►│◄────────── sign ──────────────────│ 2'. review (sign)
     │                                 │                                    │
     │   3. submit private data        │                                    │
     │──► data submit ─── POST /data ─►│◄──── data submit ─────────────────│ 3'. submit private data
     │                                 │                                    │
     │                                 │── execute plan inside enclave ──   │
     │                                 │                                    │
     │◄─── results ─── GET /results ──►│── results ────────────────────────►│
```

### Who sees what

```
                       ┌───────────────────────────────────┐
                       │         TEE enclave               │
                       │  (attested hardware — the only    │
                       │   place both data sets exist)     │
                       │                                   │
                       │   sees:  plan, data1, data2,      │
                       │          step outputs, results    │
                       └───────────────────────────────────┘
                                 ▲                ▲
                     TLS-sealed  │                │  TLS-sealed
                     to enclave  │                │  to enclave
                     pubkey      │                │  pubkey
                                 │                │
    ┌─────────────────────┐      │                │      ┌─────────────────────┐
    │      Party A        │      │                │      │      Party B        │
    │                     │──────┘                └──────│                     │
    │  sees:              │                              │  sees:              │
    │   • the plan        │                              │   • the plan        │
    │   • data1 (own)     │                              │   • data2 (own)     │
    │   • final results   │                              │   • final results   │
    │                     │                              │                     │
    │  does NOT see:      │                              │  does NOT see:      │
    │   • data2           │                              │   • data1           │
    │   • B's secret key  │                              │   • A's secret key  │
    └─────────────────────┘                              └─────────────────────┘

    TEE host, network, GitHub, anyone watching public traffic:
      sees:    plan contents, plan_hash, both public keys, both signatures,
               ciphertext in transit, final results (if the plan publishes them)
      never:   data1, data2, either party's secret key,
               intermediate step outputs (unless the plan returns them)
```

- **The plan is the contract.** It specifies both parties' expected public keys, the declared shape of each side's data, and the exact sequence of Python / LLM steps that will run. `plan_hash = sha256(canonical_json(plan))` identifies it uniquely.
- **Both parties sign the hash** with their ed25519 private key. The TEE refuses to execute unless both signatures verify against the public keys committed at plan creation.
- **Each party submits their data privately.** The submission is signed (`sha256("auditor-submit:v1:" || plan_hash || sha256(data))`) so an eavesdropper who sees the public key can't impersonate the submitter.
- **Computation runs inside the enclave.** Outputs defined by the plan come back; nothing else escapes.

The separation between signing the plan and submitting data is deliberate: it lets each party review the full computation before committing any data, and it lets signing happen well before data is available (or on a colder machine that holds the key).

## Install

```bash
pip install -e /path/to/auditor-in-a-TEE/cli
# or for isolation:
pipx install /path/to/auditor-in-a-TEE/cli
```

Requires Python ≥3.10.

## End-to-end example: OpenAI chat usage audit

This is the `openai_audit` template. A user has opted in to let OpenAI researchers analyze ChatGPT usage patterns for aggregate research (modeled on the "How People Use ChatGPT" paper). The user keeps their conversation logs private; OpenAI submits research queries. The TEE runs approved queries and returns only aggregate statistics — no conversation text, no re-identification, no PII.

We'll run both sides on one machine for demonstration. In reality each party runs the CLI on their own machine with their own private key.

### 0. Start the TEE server (or point at a deployed one)

For local development:

```bash
cd auditor-in-a-TEE/webapp
REQUIRE_SIGNATURES=true python3 -m uvicorn api_server:app --port 8088
```

For a real deployed enclave, first verify the attestation matches the public deployer repo:

```bash
tinfoil attestation verify \
  -e your-enclave-host.tinfoil.dev \
  -r RoyRin/auditor-in-a-TEE-deployer
```

Then set the URL:

```bash
export AUDITOR_TEE_URL=https://your-enclave-host.tinfoil.dev
```

### 1. Generate a keypair for each party

```bash
# Party 1 (the user)
auditor keygen --out ~/.auditor/keys/alice.json

# Party 2 (OpenAI research)
auditor keygen --out ~/.auditor/keys/openai.json
```

Capture the public keys:

```bash
ALICE_PK=$(python3 -c 'import json;print(json.load(open("'$HOME'/.auditor/keys/alice.json"))["public_key"])')
OAI_PK=$(python3   -c 'import json;print(json.load(open("'$HOME'/.auditor/keys/openai.json"))["public_key"])')
echo "alice:  $ALICE_PK"
echo "openai: $OAI_PK"
```

In a real deployment these two commands run on different machines. Alice sends her public key to OpenAI (or vice versa) over any public channel — public keys are not secrets.

### 2. Create the plan from the shipped template

```bash
mkdir -p /tmp/openai-audit && cd /tmp/openai-audit
auditor plan template openai_audit --out plan.yaml
```

Edit `plan.yaml`: replace `deadbeef...` with `$ALICE_PK` and `cafebabe...` with `$OAI_PK`. Or do it programmatically:

```bash
sed -i.bak "s/$(printf 'deadbeef%.0s' {1..8})/$ALICE_PK/g; s/$(printf 'cafebabe%.0s' {1..8})/$OAI_PK/g" plan.yaml
```

If the LLM steps should actually call a model, set `tinfoil_api_key: your-key-here` in the YAML (or leave as `null` to see the rendered prompts without calling out).

Create the plan on the TEE:

```bash
auditor plan create plan.yaml --url http://127.0.0.1:8088
```

Output:

```
Plan created
  plan_id:   a1b2c3d4
  plan_hash: <64 hex>
  name:      OpenAI Chat Usage Audit
  url:       http://127.0.0.1:8088
  state:     ./.auditor/state.json
```

The `plan_id` is saved to `./.auditor/state.json` so subsequent commands don't need `--plan-id`.

### 3. Both parties review and sign

Review:

```bash
auditor plan show
```

This prints the full plan with both expected public keys, the step definitions, and current signature / data status. Both parties inspect the prompt templates, constitutions, and Python code here — this is the last moment before anyone commits.

Sign (each party runs their own command on their own machine):

```bash
# Alice
auditor plan sign --user user1 --key ~/.auditor/keys/alice.json

# OpenAI
auditor plan sign --user user2 --key ~/.auditor/keys/openai.json
```

The CLI first verifies that the keypair you loaded matches the plan's `expected_keys[user1]` (or `user2`) — if you point it at the wrong key it refuses before sending anything. The signature is over the canonical plan bytes.

After both signatures land, the plan status flips to `signed`.

### 4. Submit private data

Sample conversation logs for Alice and research queries for OpenAI:

```bash
cat > alice-conversations.json <<'JSON'
[
  {"id":"c1","timestamp":"2024-03-11","context":"work","messages":[{"role":"user","content":"Debug this Python IndexError"},{"role":"assistant","content":"..."}]},
  {"id":"c2","timestamp":"2024-03-11","context":"personal","messages":[{"role":"user","content":"Write a poem about the ocean"},{"role":"assistant","content":"..."}]},
  {"id":"c3","timestamp":"2024-03-12","context":"work","messages":[{"role":"user","content":"Explain SQL INNER JOIN vs LEFT JOIN"},{"role":"assistant","content":"..."},{"role":"user","content":"What about FULL OUTER?"},{"role":"assistant","content":"..."}]},
  {"id":"c4","timestamp":"2024-03-12","context":"work","messages":[{"role":"user","content":"Draft an email to my manager"},{"role":"assistant","content":"..."}]},
  {"id":"c5","timestamp":"2024-03-13","context":"personal","messages":[{"role":"user","content":"Probability of rolling a 6 with three dice?"},{"role":"assistant","content":"..."},{"role":"user","content":"Show the formula"},{"role":"assistant","content":"..."}]},
  {"id":"c6","timestamp":"2024-03-13","context":"work","messages":[{"role":"user","content":"Review this React component for re-renders"},{"role":"assistant","content":"..."}]},
  {"id":"c7","timestamp":"2024-03-14","context":"personal","messages":[{"role":"user","content":"Short sci-fi story about Mars"},{"role":"assistant","content":"..."}]},
  {"id":"c8","timestamp":"2024-03-14","context":"work","messages":[{"role":"user","content":"Analyze these sales numbers"},{"role":"assistant","content":"..."},{"role":"user","content":"Summary table please"},{"role":"assistant","content":"..."}]}
]
JSON

cat > openai-queries.json <<'JSON'
{
  "researcher": "OpenAI Research Team",
  "queries": [
    {"id":"q1","question":"What percentage of conversations are work vs personal?","type":"work_personal_split"},
    {"id":"q2","question":"Distribution of use-case categories?","type":"use_case_distribution"},
    {"id":"q3","question":"Average turns per conversation by category?","type":"multi_turn_analysis"}
  ]
}
JSON
```

Submit:

```bash
# Alice (user1) submits her logs
auditor data submit --user user1 --key ~/.auditor/keys/alice.json --data alice-conversations.json

# OpenAI (user2) submits the research queries
auditor data submit --user user2 --key ~/.auditor/keys/openai.json --data openai-queries.json
```

Stdin works too: `cat alice-conversations.json | auditor data submit --user user1 --key ... --data -`.

After both submissions the plan status is `data_ready`.

### 5. Run the computation

Anyone who has the plan_id and URL can trigger execution — nothing private is sent here, the data is already inside the enclave:

```bash
auditor run
```

The `openai_audit` plan has three LLM steps:

1. Compliance check: verifies OpenAI's queries fall within the approved types.
2. Analysis: classifies conversations into use-case categories, computes aggregates, suppresses any category with <3 conversations (k-anonymity).
3. Final review: re-checks the output against every constitutional rule before releasing it.

Both parties get the same output:

```bash
auditor results --json > results.json
```

The `--json` flag is useful for piping into `jq` or feeding into downstream analysis.

## Reference

### Command table

| Command | What it does |
|---|---|
| `auditor keygen [--out PATH] [--force]` | Generate an ed25519 keypair |
| `auditor plan template {salary,openai_audit} [--out FILE] [--force]` | Write a built-in plan template to disk |
| `auditor plan create FILE.yaml [--url URL]` | POST the plan, save `plan_id` to `./.auditor/state.json` |
| `auditor plan show [PLAN_ID] [--url URL] [--json]` | Fetch and render a plan |
| `auditor plan sign --user {user1,user2} [--key PATH] [--plan-id ID] [--url URL]` | Sign the plan as a specific party |
| `auditor data submit --user {user1,user2} --data {FILE\|-} [--key PATH] [--plan-id ID]` | Sign and submit private data |
| `auditor run [--plan-id ID] [--url URL] [--json]` | Execute the plan |
| `auditor results [--plan-id ID] [--url URL] [--json]` | Re-fetch results |

### Configuration precedence

For each of `--url`, `--plan-id`, `--key`: flag > environment variable > `./.auditor/state.json` > error.

| Setting | Flag | Env | Default / state |
|---|---|---|---|
| TEE URL | `--url` | `AUDITOR_TEE_URL` | state file |
| Plan ID | `--plan-id` | `AUDITOR_PLAN_ID` | state file |
| Key path | `--key` | `AUDITOR_KEY` | `~/.auditor/keys/default.json` |

### File layout

- `~/.auditor/keys/*.json` — your ed25519 keypairs, mode 0600. Format:
  ```json
  {"version": 1, "alg": "ed25519", "public_key": "<64 hex>", "secret_key": "<64 hex>"}
  ```
- `./.auditor/state.json` — per-project state from `plan create`. Safe to delete; you'll just need to pass `--plan-id` and `--url` explicitly afterward.

### What gets signed

- **Plan signature**: `ed25519(secret, canonical_plan_bytes(plan))` where `canonical_plan_bytes` is `json.dumps(payload, sort_keys=True).encode()` over the fixed field set `{name, user1_public_key, user2_public_key, data1_format, data2_format, steps, scripts}`. Deterministic — same plan always produces the same bytes.
- **Data submission signature**: `ed25519(secret, "auditor-submit:v1:" || plan_hash_bytes || sha256(data))`. The domain-separator prefix prevents a plan signature from being replayed as a data signature. Hashing `data` keeps the signed message small regardless of payload size.

### Templates

Ship-bundled plan templates: `salary` (competitive salary benchmarking) and `openai_audit` (above). Run `auditor plan template <name> --out some.yaml` to get a starting point.

### Server URLs

- `POST /plan` — create
- `GET  /plan/{id}` — review (redacts submitted data and signature bytes)
- `POST /plan/{id}/sign` — submit a signature
- `POST /plan/{id}/data` — submit signed private data
- `POST /plan/{id}/run` — execute
- `GET  /plan/{id}/results` — fetch results
- `GET  /health`

### Strict signature mode

The server exposes `REQUIRE_SIGNATURES` as an environment variable. In production this defaults to `true`: signatures on `/sign` and `/data` are verified, and requests without a valid signature get 403. Set `REQUIRE_SIGNATURES=false` for local development or for compatibility with legacy clients that don't sign.
