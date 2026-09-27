# OpsMind

### Human-in-the-Loop Self-Learning SRE Copilot

> **AI investigates. AI analyzes. AI recommends. Human decides. Systems execute. AI learns from the outcome.**

OpsMind is an AI-assisted Site Reliability Engineering platform. When a production service misbehaves,
OpsMind gathers the evidence, recalls how similar incidents were handled before, proposes a
**pre-approved** remediation runbook, asks a human for approval (dashboard or Slack), executes the
approved action through Ansible, verifies recovery with real metrics — and stores the entire experience
in **[Hindsight](https://github.com/vectorize-io/hindsight)** so the next recommendation is better.

Built for **HackwithHyderabad 3.0** — theme: *"AI Agents That Learn Using Hindsight"*.
Runs entirely on a laptop at **₹0** (Docker, self-hosted Hindsight, optional free-tier LLMs).

▶️ **How to run it (step by step):** [RUN.md](RUN.md) ·
📘 **Tech stack, architecture and every command:** [TECH_STACK.md](TECH_STACK.md) ·
🎬 **Live demo script:** [docs/demo.md](docs/demo.md)

---

## Table of contents

1. [The problem](#1-the-problem)
2. [What OpsMind does](#2-what-opsmind-does)
3. [Philosophy: not autonomous, on purpose](#3-philosophy-not-autonomous-on-purpose)
4. [How OpsMind learns](#4-how-opsmind-learns)
5. [The demo — measured results](#5-the-demo--measured-results)
6. [Safety model](#6-safety-model)
7. [Project status](#7-project-status)
8. [Quick start](#8-quick-start)
9. [Repository layout](#9-repository-layout)
10. [How this maps to the judging criteria](#10-how-this-maps-to-the-judging-criteria)
11. [Documentation index](#11-documentation-index)

---

## 1. The problem

When an alert fires, an on-call engineer spends most of their time on work that is **repetitive**,
not difficult:

```
ALERT → open dashboards → read logs → compare metrics → check recent deploys
      → search old tickets/postmortems → form a hypothesis → write a runbook
      → get a review → execute → watch metrics → write the postmortem
```

Worse, the knowledge gained is fragile. The engineer who knew *"don't flush the whole cache — only the
stale session keys"* is asleep, on leave, or has changed teams. The next person repeats the investigation
from scratch — and may repeat the mistake.

**OpsMind removes the repetitive overhead and turns every incident into organizational memory.**

## 2. What OpsMind does

Every incident runs through one traceable [LangGraph](https://langchain-ai.github.io/langgraph/) workflow:

| # | Node | What happens | Who |
|---|---|---|---|
| 1 | **Intake** | Prometheus alert (via Alertmanager) or manual trigger becomes an incident | System |
| 2 | **Evidence** | `get_metrics`, `get_logs`, `get_service_health`, `get_recent_deployments`, `get_git_changes` → deterministic findings | Controlled tools |
| 3 | **Recall** | Ask Hindsight for similar incidents, what worked, what failed, what operators said — *before* diagnosing | Hindsight |
| 4 | **Diagnosis** | Root cause, category, confidence, evidence — one structured LLM call, or the rule engine | Gemini / Groq / rules |
| 5 | **Planner** | Validate the chosen runbook ID against the catalog; risk & policy gate; strategy score | Code |
| 6 | **Approval** ⏸ | The graph **stops**. Approve / Edit / Reject / Execute manually | **Human** |
| 7 | **Execution** | Ansible **dry run first**, then the real run | Ansible / Jenkins |
| 8 | **Verification** | Poll Prometheus until P95, hit ratio and health recover — before vs after | Code |
| 9 | **Learning** | Postmortem + lesson retained in Hindsight; strategy scores updated | Hindsight |

Every step appears in the incident's trace as concise operational reasoning (never hidden chain-of-thought).
From the real run:

```
✓ evidence   P95 latency is 2.2 s vs a baseline of 5 ms (461× higher).
             Redis memory is at 100% of its limit. Cache hit ratio is 38%.
             220 'cache write rejected' warnings (Redis maxmemory) in the last 5 min.
             auth-service v2.4.0 was deployed 1 min ago (Refactor session storage to Redis hashes).
✓ recall     Hindsight recalled 1 memories (1 past incidents)
             INC-1001: operator overruled RB-CACHE-002 → RB-CACHE-001 ("Do not clear the entire cache …")
✓ planner    Proposed RB-CACHE-001 (Targeted stale-session cache cleanup), risk LOW — strategy score 1.00
```

## 3. Philosophy: not autonomous, on purpose

OpsMind is **not** an agent that "fixes production by itself". That would be unsafe, and no real SRE team
would trust it.

- The **AI** is fast at reading evidence, searching history and drafting a plan.
- The **human** holds context the AI can't see ("that Redis also stores active sessions") and owns the decision.
- **Systems** (Ansible, Jenkins) execute only vetted, versioned runbooks.
- **Hindsight** makes sure the human's judgement is remembered and applied next time.

## 4. How OpsMind learns

**Mechanism:** *human-in-the-loop learning through persistent operational memory and remediation outcomes.*

After every incident, the Learning node retains a structured record in Hindsight:

```
Incident → symptoms & evidence → AI diagnosis → AI recommendation
        → human decision (approved / modified / rejected) → the human's comment
        → executed action → verification (real metrics) → lesson
```

— as narrative text (what Hindsight embeds and searches) plus metadata (`recommended_runbook`,
`final_runbook`, `decision`, `outcome`, `operator_comment`, P95 before/after).

On the next incident, **recall happens before diagnosis**. OpsMind turns the recalled memories into
guidance — *preferred* runbooks (verifiably resolved a similar incident) and *overruled* runbooks
(humans rejected or replaced them, and why). The LLM prompt and the rule engine both use it, the policy
gate raises the risk of overruled runbooks, and a **strategy score** per runbook
(`succeeded ÷ (proposed + adopted)`) is shown as supporting evidence.

> **Terminology:** Hindsight is a memory system. It does **not** do reinforcement learning, and OpsMind
> trains no model. Improvement comes from recalled experience and verified outcomes.

## 5. The demo — measured results

Scenario: an **auth-service deploy drops the TTL on user sessions**. Sessions pile up in the shared
Redis; Redis (`volatile-lru`) may only evict keys that *have* a TTL — product-api's cache — so every
product request becomes a slow database query and latency explodes. 300 of the sessions belong to users
who are **active right now**: flushing the cache would fix latency *and log them all out*.

Clean run from a blank memory, 50 req/s steady traffic, Windows 11 + Docker Desktop:

| | **INC-1001** — first time | **INC-1002** — same incident again |
|---|---|---|
| Evidence | P95 2.2 s vs 5 ms baseline (461×), Redis 100 %, hit ratio 38 % | same pattern |
| Hindsight recall | *no similar past incidents* | **INC-1001 + the operator's exact words** |
| AI recommendation | `RB-CACHE-002` full cache flush | **`RB-CACHE-001` targeted stale-session cleanup** |
| Risk / confidence | **HIGH** / 80 % | **LOW** / 92 % |
| Human | **Modified** → RB-CACHE-001: *"Do not clear the entire cache — this Redis also holds active user sessions. Only remove stale session keys."* | **Approved** (one click) |
| Execution (Ansible) | dry run → 19,156 stale / 300 active; apply → 19,156 deleted, 300 kept | same |
| Verified by Prometheus | **P95 4.6 s → 313 ms**, hit ratio 18 % → 93 %, Redis 100 % → 6 % | **P95 4.9 s → 276 ms**, hit ratio 8 % → 96 % |
| Strategy score after | RB-CACHE-001 **1.00**, RB-CACHE-002 **0.00** | RB-CACHE-001 **1.00** (2 successes) |

**Same problem, better first recommendation, less human effort — because of Hindsight.**

Step-by-step script with talking points: [docs/demo.md](docs/demo.md).

## 6. Safety model

```
LLM proposes a runbook ID → policy / risk gate → human approval → vetted playbook
                         → Ansible --check (dry run) → Ansible apply → verify with real metrics
```

OpsMind **never**:

- executes LLM-generated commands — the LLM can only name an ID from the catalog; an invented ID is
  rejected by code, and every parameter is validated against declared type / bounds / allowlist
- executes anything without a human decision (the graph is paused at an interrupt)
- runs `terraform apply`, changes security groups, deletes databases, or restarts services on its own
- declares success from an exit code — **success is proven by Prometheus**

| Runbook | Action | Risk | Executor |
|---|---|---|---|
| `RB-CACHE-001` | Delete sessions idle > `max_idle_hours` (1–720, default 24) | LOW | Ansible → Redis |
| `RB-CACHE-002` | Full cache flush (`FLUSHDB`) | HIGH | Ansible → Redis |
| `RB-SERVICE-001` | Restart the product-api container (allowlisted) | MEDIUM | Ansible → Docker API |
| `RB-DEPLOY-001` | Roll back to the previous build | MEDIUM | Ansible → Jenkins |

Graceful degradation — each verified by tests: LLM missing / rate-limited / malformed → rule engine;
Hindsight down → continue without history, record kept in the DB; Prometheus down → "missing evidence";
Slack down → dashboard approval; dry run fails → abort before apply; execution timeout; invalid runbook
or parameters → HTTP 422; two approvers at once → HTTP 409.

## 7. Project status

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Project foundation | ✅ |
| 1 | product-api + Redis + PostgreSQL, JSON logs, Prometheus metrics | ✅ |
| 2 | Deterministic incident simulator + fixed-rate load generator + demo reset | ✅ |
| 3 | Prometheus, Alertmanager, Grafana dashboard, `HighLatency` alert → OpsMind | ✅ |
| 4 | LangGraph workflow: 9 nodes, typed state, Postgres checkpointer, human interrupt | ✅ |
| 5 | Controlled evidence tools with a uniform result contract | ✅ |
| 6 | Self-hosted Hindsight retain / recall | ✅ |
| 7 | Runbook catalog + parameter validation + policy gate | ✅ |
| 8 | Approval states: Approve / Modify / Reject / Execute manually | ✅ |
| 9 | Slack: incident message with buttons (Socket Mode, no public URL) | ✅ built & unit-tested; needs your Slack tokens to run live |
| 10 | Ansible execution with `--check` dry run | ✅ |
| 11 | Jenkins: test → build `build-N` → deploy → smoke test → report; rollback job | ✅ |
| 12 | Metric-based verification (before vs after) | ✅ |
| 13 | Learning loop — second incident gets the better recommendation | ✅ |
| 14 | Strategy scoring | ✅ |
| 15 | React + TypeScript dashboard | ✅ |
| — | Gemini / Groq diagnosis | ✅ built & unit-tested; add a free API key to use it (rule engine otherwise) |
| — | Terraform | not started (deliberately out of MVP scope) |

**Tests** (all enforce ≥ 80 % coverage): backend 126 tests (94 %), product-api 24 (96 %),
incident-simulator 38 (97 %), dashboard 21 (98 % lines).

## 8. Quick start

Requires Windows 11 + Docker Desktop (WSL2) + Python 3.11 (+ Node 24 only to develop the dashboard).

```powershell
Copy-Item .env.example .env          # first time only — defaults work, keys are optional
docker compose up -d --build         # 9 containers; first run downloads ~5 GB (Hindsight is 3.6 GB)
```

| Open | URL |
|---|---|
| OpsMind dashboard | <http://127.0.0.1:3002> |
| Grafana | <http://127.0.0.1:3001> |
| OpsMind API docs | <http://127.0.0.1:8002/docs> |
| Hindsight UI | <http://127.0.0.1:9999> |

Then run the demo (one-time simulator setup in [TECH_STACK.md §7.3](TECH_STACK.md#73-incident-simulator-one-time-setup)):

```powershell
cd incident-simulator
.\.venv\Scripts\python.exe load_generator.py --duration 1200      # terminal 1: keep running
.\.venv\Scripts\python.exe create_incident.py --type cache        # terminal 2: after ≥ 2 min
```

→ watch INC-1001 appear in the dashboard, edit it to `RB-CACHE-001`, then inject again for INC-1002.

## 9. Repository layout

```
OpsMind/
├── backend/                  # OpsMind orchestrator — FastAPI + LangGraph
│   ├── app/agents/           #   graph, typed state, 9 nodes, rule engine, memory guidance, verdict
│   ├── app/tools/            #   evidence tools (metrics, logs, health)
│   ├── app/services/         #   Hindsight, LLM, runbooks, policy, executor, Slack, stores, workflow
│   ├── app/api/              #   /v1/alerts, /v1/incidents, /v1/runbooks, /v1/strategies, /v1/memories, /v1/deployments
│   └── tests/                #   workflow, services, API, runbook scripts, Postgres integration
├── frontend/                 # React + TypeScript dashboard (Vite, served by nginx)
├── product-api/              # The "production" service OpsMind watches
├── incident-simulator/       # create_incident.py, load_generator.py, reset_demo.py
├── runbooks/                 # RB-*.yml — the ONLY actions the AI may propose
├── infrastructure/
│   ├── ansible/              #   playbooks + scripts executed for each runbook
│   ├── jenkins/              #   image, config-as-code, deploy & rollback pipelines
│   └── slack/                #   Slack app manifest (Socket Mode)
├── monitoring/               # Prometheus config + alert rules, Alertmanager, Grafana dashboard
├── docs/                     # architecture.md, setup.md, demo.md
├── docker-compose.yml
├── .env.example
├── README.md · TECH_STACK.md · CHANGELOG.md
```

## 10. How this maps to the judging criteria

| Criterion | Weight | Evidence in OpsMind |
|---|---|---|
| **Innovation** | 30 % | Human corrections become durable, recallable knowledge that changes the next plan; a copilot with a hard safety gate instead of an unsafe autopilot |
| **Hindsight Memory** | 25 % | Memory is on the critical path: recall runs *before* diagnosis and changes runbook, risk and confidence (INC-1001 vs INC-1002 above); every decision and verified outcome is retained |
| **Technical Implementation** | 20 % | Real instrumented service and reproducible incident; LangGraph with typed state, Postgres checkpointing and a human interrupt; structured LLM output with fallback; Ansible dry-run → apply; metric verification; 209 tests with coverage gates |
| **User Experience** | 15 % | One-glance incident summary, live trace, Approve / Edit / Reject / Manual in the dashboard or Slack, learning page with strategy scores and memory search |
| **Real-world Impact** | 10 % | Minutes of repetitive investigation become seconds; tribal knowledge survives people changing teams; runs at ₹0 |

## 11. Documentation index

| Document | Contents |
|---|---|
| [RUN.md](RUN.md) | Step-by-step commands to run the whole demo |
| [TECH_STACK.md](TECH_STACK.md) | Technology choices, architecture diagrams, component internals, every command, troubleshooting |
| [docs/architecture.md](docs/architecture.md) | Design decisions and why |
| [docs/setup.md](docs/setup.md) | Step-by-step setup, including optional Gemini, Slack and Jenkins |
| [docs/demo.md](docs/demo.md) | Live demo script with talking points |
| [CHANGELOG.md](CHANGELOG.md) | What changed, phase by phase |
