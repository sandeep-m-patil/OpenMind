# OpsMind

### Human-in-the-Loop Self-Learning SRE Copilot

> **AI investigates. AI analyzes. AI recommends. Human decides. Systems execute. AI learns from the outcome.**

OpsMind is an AI-assisted Site Reliability Engineering platform. When a production service misbehaves,
OpsMind gathers the evidence, recalls how similar incidents were handled before, proposes a
**pre-approved** remediation runbook, asks a human for approval in Slack, executes the approved action
through controlled automation, verifies recovery with real metrics — and stores the entire experience
in **Hindsight** memory so the next recommendation is better.

Built for **HackwithHyderabad 3.0** — theme: *"AI Agents That Learn Using Hindsight"*.
Runs entirely on a laptop at **₹0** (Docker + free LLM tiers).

📘 **Tech stack, architecture and every command:** [TECH_STACK.md](TECH_STACK.md)

---

## Table of contents

1. [The problem](#1-the-problem)
2. [What OpsMind does](#2-what-opsmind-does)
3. [Philosophy: not autonomous, on purpose](#3-philosophy-not-autonomous-on-purpose)
4. [How OpsMind learns](#4-how-opsmind-learns)
5. [The demo story](#5-the-demo-story)
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

Worse, the knowledge gained is fragile. The engineer who knew *"don't flush the whole cache — only
the stale session keys"* is asleep, on leave, or has changed teams. The next person repeats the
investigation from scratch — and may repeat the mistake.

**OpsMind removes the repetitive overhead and turns every incident into organizational memory.**

## 2. What OpsMind does

For every incident, OpsMind runs one traceable workflow:

| # | Step | Who does it |
|---|---|---|
| 1 | **Intake** — receive the alert (service, severity, symptom) | System |
| 2 | **Evidence** — collect logs, metrics, service health, recent deployments, git changes | Controlled tools |
| 3 | **Recall** — ask Hindsight for similar past incidents, what worked, what failed, operator preferences | Hindsight |
| 4 | **Diagnosis** — probable root cause, confidence score, supporting evidence | LLM (structured output) |
| 5 | **Runbook plan** — select a *pre-approved* runbook ID, estimate risk | LLM picks, code validates |
| 6 | **Policy gate** — deterministic risk/policy checks | Code |
| 7 | **Human approval** — Approve / Edit / Reject / Execute manually, via Slack | **Human** |
| 8 | **Execution** — run the approved runbook through Ansible / Jenkins | Controlled tools |
| 9 | **Verification** — compare before vs after using real metrics | Code |
| 10 | **Learning** — write a postmortem and retain the full experience in Hindsight | Hindsight |

Every step is visible in an execution trace, with concise operational reasoning — for example:

```
✓ Redis memory reached 100% (limit 32 MB); 2,715 keys evicted
✓ P95 latency rose from 13 ms to 6.9 s (≈500×); cache hit ratio fell from 100% to 5%
✓ Similar incident INC-812 was resolved with RB-CACHE-001 (targeted stale-session cleanup)
✓ auth-service was deployed 7 minutes before the alert
```

(The hidden chain-of-thought is never exposed — only evidence and conclusions.)

## 3. Philosophy: not autonomous, on purpose

OpsMind is **not** an autonomous agent that "fixes production by itself". That would be unsafe and
would not be trusted by real SRE teams.

- The **AI** is fast at reading evidence, searching history and drafting a plan.
- The **human** holds context the AI can't see ("that cache also stores active sessions") and owns
  the decision.
- **Systems** (Ansible, Jenkins) execute only vetted, versioned runbooks.
- **Hindsight** makes sure the human's judgement is remembered and applied next time.

> AI doesn't replace the SRE engineer. It removes repetitive investigation and execution overhead.
> Human expertise stays in the loop. Every incident becomes organizational memory.
> Every human correction makes future recommendations better.

## 4. How OpsMind learns

**Learning mechanism:** *human-in-the-loop learning through persistent operational memory and
remediation outcomes.*

After every incident OpsMind retains a structured learning record in Hindsight:

```
Incident → Symptoms → Evidence → AI diagnosis → AI recommendation
        → Human decision (approved / modified / rejected) → Human modification
        → Executed action → Verification result (real metrics) → Lesson learned
```

On the next incident, the **recall** step retrieves these records *before* the diagnosis is made,
so the model reasons with:

- similar past incidents and their root causes
- remediations that **succeeded** — and ones that **failed**
- **operator corrections** (e.g. "targeted cleanup, not a full flush")
- verified before/after metrics

The agent's recommendation therefore changes because of memory — that is the visible improvement.

Later (Phase 14), a lightweight **strategy score** per remediation strategy — built from counts of
approvals, modifications, rejections, successes and failures — will be shown as supporting evidence.

> **Terminology note:** Hindsight is a memory system. It does **not** perform reinforcement learning,
> and OpsMind does not train a neural network. Improvement comes from recalled experience and outcomes.

## 5. The demo story

The primary scenario is **cache saturation** on `product-api`, which is already reproducible today.

### What goes wrong

A deploy of the auth-service drops the TTL (expiry) on user-session keys. Sessions pile up in the
shared Redis forever. Redis is configured to evict only keys *with* a TTL — so when memory fills,
it evicts product-api's cache instead. Every product request becomes a cache miss that costs a slow
database query, traffic keeps arriving faster than the service can now handle, and latency explodes.

Measured on the local stack at 50 requests/second:

| | Healthy | During incident |
|---|---|---|
| P95 latency | **13 ms** | **6.9 s** |
| Cache hit ratio | 100% | ~5% |
| Redis memory | 4% | 100% |
| Logs | quiet | `cache write rejected … used memory > 'maxmemory'`, `slow request` |

There is a trap: **300 of the sessions belong to users who are active right now.** Flushing the whole
cache fixes latency *and logs every one of them out*.

### Incident #1 — the AI learns from the human

1. Monitoring detects high latency → OpsMind opens an incident.
2. OpsMind collects the evidence above. Hindsight has nothing relevant yet.
3. AI diagnosis: *Redis cache saturation* (confidence e.g. 80%). Recommendation: *clear the cache.*
4. Slack message → the engineer **edits**: *"Don't clear the entire cache. Only remove stale session keys."*
5. The modified runbook `RB-CACHE-001` (targeted stale-session cleanup) runs via Ansible.
6. Verification with real metrics: P95 6.9 s → ~20 ms. Active users stay logged in. **Resolved.**
7. The full experience — including the human correction — is retained in Hindsight.

### Incident #2 — the AI remembers

The same incident is triggered again. This time recall returns incident #1, and OpsMind says:

> *"A similar incident was previously resolved using targeted session-key cleanup. The previous
> operator rejected a full cache purge because it was unnecessarily broad and would log out active
> users. The targeted cleanup reduced P95 latency from 6.9 s to ~20 ms. I recommend RB-CACHE-001."*

The engineer approves with one click. **Same problem, better first recommendation, less human effort
— because of Hindsight.**

## 6. Safety model

```
AI proposal → policy / risk gate → human approval → controlled tool → execution → verification
```

OpsMind will **never**:

- execute arbitrary LLM-generated shell commands — the LLM can only choose a **runbook ID**
  (e.g. `RB-CACHE-001`); the backend loads the vetted runbook
- execute remediation without human approval
- run `terraform apply`, modify infrastructure or security groups automatically
- delete databases or restart critical systems automatically
- declare success because a command returned exit code 0 — **success is proven by metrics**

Initial runbooks (Phase 7):

| ID | Action | Risk |
|---|---|---|
| `RB-CACHE-001` | Targeted stale-session cache cleanup | Low |
| `RB-SERVICE-001` | Restart application service | Medium |
| `RB-DEPLOY-001` | Roll back deployment | Medium |

Failures are handled explicitly (LLM or rate-limit errors, Hindsight/Slack/Jenkins unavailable,
malformed LLM output, invalid runbook, execution timeout) — never silently.

## 7. Project status

OpsMind is built incrementally — one working vertical slice before expanding.

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Project foundation (structure, docs, config) | ✅ Done |
| 1 | Local production environment: product-api + Redis + PostgreSQL, logs, metrics | ✅ Done |
| 2 | Deterministic incident simulator (cache saturation) + fixed-rate load generator | ✅ Done |
| 3 | Prometheus + Grafana dashboard + high-latency alert | ⏭ Next |
| 4 | LangGraph investigation workflow (typed state, structured LLM output) | Planned |
| 5 | Controlled evidence tools (`get_logs`, `get_metrics`, …) | Planned |
| 6 | Hindsight (self-hosted) retain / recall | Planned |
| 7 | Pre-approved runbook system | Planned |
| 8 | Human-in-the-loop approval states | Planned |
| 9 | Slack integration | Planned |
| 10 | Ansible execution (with check/dry-run mode) | Planned |
| 11 | Jenkins CI/CD + deploy correlation | Planned |
| 12 | Metric-based verification | Planned |
| 13 | Learning loop (second-incident demo) | Planned |
| 14 | Strategy scoring | Planned |
| 15 | React dashboard | Planned |

**Milestones:** ① app + cache incident + logs + metrics + Gemini diagnosis + runbook proposal →
② Hindsight → ③ human approval → ④ Ansible → ⑤ Slack → ⑥ Jenkins → ⑦ learning loop → ⑧ dashboard.

Tests: product-api 24 tests (97% coverage), incident-simulator 31 tests (98% coverage).

## 8. Quick start

Requires Windows 11 + Docker Desktop (WSL2 backend) + Python 3.11. Run in PowerShell from the
project folder.

```powershell
Copy-Item .env.example .env                  # first time only
docker compose up -d --build                 # start Redis, PostgreSQL, product-api
curl.exe http://127.0.0.1:8001/health        # expect "status":"ok"
```

Reproduce the incident (from `incident-simulator\`, after the one-time venv setup in
[TECH_STACK.md §7.4](TECH_STACK.md#74-incident-simulator)):

```powershell
.\.venv\Scripts\python.exe load_generator.py --duration 20                # healthy
.\.venv\Scripts\python.exe create_incident.py --type cache                # break it
.\.venv\Scripts\python.exe load_generator.py --duration 20 --no-warmup    # see the incident
.\.venv\Scripts\python.exe create_incident.py --type cache --restore      # reset
```

Every command, with expected output and troubleshooting: **[TECH_STACK.md](TECH_STACK.md)**.

## 9. Repository layout

```
OpsMind/
├── product-api/              # The "production" service OpsMind watches
│   ├── app/                  #   FastAPI app: cache, db, service, metrics, middleware, logging
│   ├── tests/                #   unit tests (fakes) + integration tests (live containers)
│   ├── Dockerfile
│   └── requirements*.txt
├── incident-simulator/       # Deterministic incidents + load
│   ├── create_incident.py    #   --type cache [--status | --restore]
│   ├── load_generator.py     #   fixed-rate traffic + latency report
│   ├── scenarios/            #   one module per incident type
│   └── tests/
├── docs/                     # architecture.md, setup.md, demo.md
├── docker-compose.yml        # local "production" environment
├── .env.example              # configuration template (copy to .env)
├── README.md                 # this file — the project
├── TECH_STACK.md             # stack, architecture, commands
└── CHANGELOG.md
```

Planned folders — `backend/` (orchestrator), `frontend/`, `runbooks/`, `monitoring/`,
`infrastructure/{ansible,jenkins,terraform}/` — are created when their phase starts.

## 10. How this maps to the judging criteria

| Criterion | Weight | How OpsMind addresses it |
|---|---|---|
| **Innovation** | 30% | Human corrections become durable, recallable operational knowledge; the AI is a copilot with a safety gate, not an unsafe autopilot |
| **Hindsight Memory** | 25% | Memory is the core of the product: recall happens *before* diagnosis and changes the recommendation; every incident, decision and outcome is retained |
| **Technical Implementation** | 20% | Real instrumented service, reproducible incident, typed LangGraph state, structured LLM output, controlled runbook IDs, metric-based verification, tests with coverage gates |
| **User Experience** | 15% | Slack-native approval (Approve / Edit / Reject / Manual), a single incident screen showing diagnosis → decision → result → lesson |
| **Real-world Impact** | 10% | Cuts repetitive investigation time; stops knowledge from being lost between engineers; runs at ₹0 |

## 11. Documentation index

| Document | Contents |
|---|---|
| [TECH_STACK.md](TECH_STACK.md) | Technology choices, architecture diagrams, component internals, all commands |
| [docs/architecture.md](docs/architecture.md) | Design decisions in depth |
| [docs/setup.md](docs/setup.md) | Step-by-step setup and troubleshooting |
| [docs/demo.md](docs/demo.md) | Live demo script with talking points |
| [CHANGELOG.md](CHANGELOG.md) | What changed, phase by phase |
