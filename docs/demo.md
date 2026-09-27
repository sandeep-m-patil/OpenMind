# OpsMind — Live Demo Script (≈ 10 minutes)

The story: **the same production incident happens twice. The second time, OpsMind recommends what the
human taught it the first time — because of Hindsight.**

## 0. Before the audience arrives (5 min)

```powershell
docker compose up -d --build                       # whole stack (add --profile cicd for Jenkins)
cd incident-simulator
.\.venv\Scripts\python.exe reset_demo.py --yes     # blank memory → next incident is INC-1001
```

Open these tabs:

| Tab | URL |
|---|---|
| OpsMind dashboard | <http://127.0.0.1:3002> |
| Grafana | <http://127.0.0.1:3001> (dashboard "OpsMind — product-api") |
| Hindsight UI (optional) | <http://127.0.0.1:9999> |
| Slack channel (if configured) | your OpsMind channel |

Start steady traffic in its **own terminal** and leave it running for the whole demo (≥ 2 minutes before
step 2, so the "normal latency" baseline is clean):

```powershell
.\.venv\Scripts\python.exe load_generator.py --duration 1200
```

## 1. The healthy system (1 min)

Grafana: P95 ≈ 10–20 ms, cache hit ratio 100 %, Redis memory ≈ 4 %.

> "product-api is a normal shop API: Redis cache in front of PostgreSQL. A cache miss costs a 250 ms
> query. Everything is green."

## 2. A developer deploys a bug (1 min)

```powershell
.\.venv\Scripts\python.exe create_incident.py --type cache
```

> "The auth-service team just shipped v2.4.0 — it stores user sessions in the shared Redis but forgot
> the TTL. Sessions pile up forever. Redis can only evict keys that have a TTL, so it evicts *our product
> cache*. Watch Grafana."

Within ~30 s: P95 → 5–9 s, hit ratio → ~3 %, Redis → 100 %. Within ~50 s the `HighLatency` alert fires.

## 3. OpsMind investigates on its own (1 min)

Dashboard → **INC-1001** appears and reaches *Pending approval* in ~10 s. Walk through the trace:

- **Evidence** — "P95 is 7 s vs a baseline of 13 ms (500×). Redis at 100 %. 500 'cache write rejected'
  warnings. auth-service v2.4.0 was deployed 1 min ago."
- **Hindsight recall** — "no similar past incidents yet". *OpsMind has no experience.*
- **Diagnosis** — Redis cache saturation, 80 %.
- **Plan** — `RB-CACHE-002` **Full cache flush**, **HIGH** risk. *The textbook answer.*

> "Notice: the AI never writes shell commands. It can only pick a runbook ID from a vetted catalog, and
> a policy gate rates the risk. Nothing runs until a human decides."

## 4. The human corrects the AI (1 min)

In the dashboard (or Slack): name → **Edit** → runbook `RB-CACHE-001` → comment:

> *Do not clear the entire cache — this Redis also holds active user sessions. Only remove stale session keys.*

→ **Submit edited action**.

> "The engineer knows something the AI can't see in metrics: 300 of those sessions belong to users who
> are logged in right now. A flush would fix latency and log them all out."

## 5. Controlled execution + real verification (1 min)

Trace shows:

- **Execution** — Ansible dry run: *would delete 19,203 stale sessions, keep 300*; then the real run.
- **Verification** — from Prometheus, not from an exit code: **P95 7.8 s → 45 ms**, hit ratio 5 % → 97 %,
  Redis 100 % → 6 %. **RESOLVED.**
- **Learning** — *"For product-api cache saturation, prefer RB-CACHE-001 over RB-CACHE-002: the operator
  replaced the AI's recommendation…"* — retained in Hindsight.

## 6. It happens again (2 min) — the moment that matters

Wait until Grafana is green again (~30 s), then:

```powershell
.\.venv\Scripts\python.exe create_incident.py --type cache
```

Open **INC-1002**:

| | INC-1001 | INC-1002 |
|---|---|---|
| Hindsight recall | nothing | **INC-1001 + the operator's exact words** |
| Recommendation | `RB-CACHE-002` flush | **`RB-CACHE-001` targeted cleanup** |
| Risk | HIGH | **LOW** |
| Confidence | 80 % | **92 %** |

> "Same problem. Different, better recommendation — and it cites *why*: 'INC-1001 was resolved with
> RB-CACHE-001; the operator rejected a full flush because Redis holds active sessions.' That came from
> Hindsight, not from a prompt I wrote."

Click **Approve**. Resolved again (P95 7.6 s → ~270 ms), 300 active users untouched.

## 7. Show the learning (1 min)

Dashboard → **Learning**:

- Strategy scores: `RB-CACHE-001` score **1.00** (adopted 1, approved 1, succeeded 2); `RB-CACHE-002` **0.00**
  (proposed 1, modified away 1).
- Search Hindsight memory: "product-api cache saturation" → the retained postmortems.

**Closing line:**

> "AI doesn't replace the SRE engineer. It removes the repetitive investigation and execution overhead.
> Human expertise stays in the loop. Every incident becomes organizational memory, and every human
> correction makes the next recommendation better."

## Optional extras

- **Slack**: with tokens configured, the Approve / Reject / Execute-manually buttons work from Slack
  (Edit opens the dashboard). The outcome is posted in the thread.
- **Jenkins** (`--profile cicd`): <http://127.0.0.1:8081> → *product-api-deploy* → Build Now. The
  deployment appears in OpsMind's evidence ("product-api build-N was deployed …"). `RB-DEPLOY-001`
  triggers *product-api-rollback*.
- **Resilience**: `docker compose stop hindsight` → OpsMind keeps working, the trace says
  "Hindsight unavailable — continuing without history". With a Gemini key, stop your network → it falls
  back to the rule engine and says so.

## If something goes wrong

| Symptom | Fix |
|---|---|
| No incident appears | Is the load generator running? The alert needs traffic. Check <http://127.0.0.1:9090/alerts> |
| Incident is mild (P95 < 1 s) | Re-run `create_incident.py --type cache` (it tops Redis up) |
| Baseline shows hundreds of ms | Traffic started too late — let it run ≥ 2 min before injecting |
| Stuck in *Verifying* | Verification needs traffic; it gives up after 150 s (*Remediation failed / inconclusive*) |
| Need a fresh start | `reset_demo.py --yes` |
