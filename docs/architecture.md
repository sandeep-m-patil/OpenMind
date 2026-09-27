# OpsMind Architecture — design decisions

Diagrams, component tables and commands live in [TECH_STACK.md](../TECH_STACK.md). This document
explains **why** the system is shaped the way it is.

## 1. Principles

1. **The AI proposes; humans decide; systems execute.** No path runs a remediation without a recorded
   human decision. The LangGraph workflow is physically paused at the approval node.
2. **The LLM never produces actions.** It returns a runbook *ID* from a catalog. Code validates the ID,
   validates every parameter (type, bounds, allowlist), and a policy gate assigns risk.
3. **Success is measured, not assumed.** Verification polls Prometheus; exit code 0 means nothing.
4. **Memory is on the critical path.** Recall runs *before* diagnosis, and its output changes the
   runbook, the risk and the confidence — not just the wording.
5. **Minimum LLM, maximum determinism.** One LLM call per incident. Everything that can be arithmetic is
   arithmetic. With no key, a rule engine keeps the full loop (including learning) working.
6. **Degrade, never crash.** Every external dependency has a stated fallback, and the trace says which
   fallback was used.

## 2. The incident scenario is causal, not faked

| Decision | Why |
|---|---|
| Cache-aside product-api with a 250 ms miss cost | cache health *causes* latency; nothing sleeps artificially in the request handler |
| 32 MB Redis with `volatile-lru` | only keys with a TTL can be evicted, so TTL-less sessions push out the product cache — a real, recognisable failure mode (with `allkeys-lru`, Redis would evict the junk and there'd be no incident) |
| 300 active + ~19k stale sessions, opaque key names | a correct fix must inspect `last_seen`; a flush "works" but logs real users out — the gap the human fills |
| Top-up with single writes after the bulk OOM | a pipelined batch's input buffer is freed after the OOM, leaving ~0.5 MB headroom and a *milder* incident; topping up makes severity identical run to run |
| Fixed-rate (open-loop) load | real users don't slow down when you do; a closed loop hid the incident (only 2.6× worse) |
| The simulator records the auth-service deploy | lets OpsMind demonstrate change correlation deterministically; Jenkins records real deploys the same way |

## 3. Workflow design

- **Nine nodes, one graph** (not nine agents): intake, evidence, recall, diagnosis, planner, approval,
  execution, verification, learning. Each is a small function with injected dependencies, so the whole
  graph runs in tests with fakes.
- **Interrupt + Postgres checkpointer**: `interrupt()` in the approval node stores the graph state in
  PostgreSQL; the decision endpoint resumes it with `Command(resume=…)`. The pause can last as long as
  the human needs and survives a backend restart.
- **Decisions are validated before resuming**: the API turns a human decision into a final action and
  re-runs the policy gate, so bad edits return HTTP 422 instead of failing inside the graph. An atomic
  status compare-and-set makes Slack and dashboard approvals race-free (second one gets 409).
- **Every node persists its output** to the `incidents` row (JSONB), which is what the dashboard polls.
  The trace is append-only via a LangGraph reducer.
- **Background execution**: the webhook returns immediately; the graph runs in a small thread pool.
  Any exception becomes an `ERROR` status with the message in the trace — never a silent loss.
- **Alert dedupe**: an open incident for a service absorbs further alerts; only `severity=critical`
  opens incidents.

## 4. Memory design

- **What is retained**: one item per incident — a narrative (what Hindsight embeds and searches) and
  string metadata (`recommended_runbook`, `final_runbook`, `decision`, `outcome`, `operator_comment`,
  P95 before/after). Tags scope recall to the service.
- **How it changes behaviour**: `memory_guidance.py` derives *preferred* runbooks (verifiably resolved a
  similar incident) and *overruled* ones (rejected or replaced, with the operator's reason). The LLM
  prompt includes both; the rule engine prefers the preferred runbook; the policy gate raises the risk of
  an overruled one.
- **Why chunks mode by default**: `HINDSIGHT_API_LLM_PROVIDER=none` needs no key and stores memories
  verbatim, which keeps the metadata intact and the demo free. LLM fact extraction is one `.env` change.
- **Strategy scoring (Phase 14)** is a counter table, not RL: `succeeded ÷ (proposed + adopted)`.

## 5. Execution design

- Runbooks are YAML (`runbooks/`), each naming a playbook in `infrastructure/ansible/playbooks/`.
- The executor builds an argv list — fixed `ansible-playbook`, fixed inventory, a playbook path that must
  resolve inside the Ansible directory, and validated parameters as a JSON `--extra-vars` document.
- Each playbook runs one script with explicit `--dry-run` / `--apply`. Ansible `--check` maps to
  `--dry-run`, so the dry run executes the real query logic without changing anything and reports what
  *would* happen ("would delete 19,156, keep 300").
- Scripts write a structured JSON report to a temp file (not scraped from Ansible's console output).
- `RB-SERVICE-001` uses the Docker Engine API with a container allowlist; `RB-DEPLOY-001` triggers the
  Jenkins rollback job with a CSRF crumb.

## 6. Security posture

| Control | Where |
|---|---|
| No LLM-authored commands | catalog IDs only; invented IDs rejected in the planner |
| Input validation at the boundary | Pydantic schemas for every request; runbook parameter validation |
| Parameterized SQL | all stores; the only dynamic identifiers (DB name, counter columns) come from regex / allowlists |
| No shell | executor and scripts use argv lists |
| Secrets | `.env` only (git-ignored); LLM keys sent in headers, never URLs |
| Network exposure | every port bound to `127.0.0.1` |
| **Accepted local-demo risks** | backend and Jenkins mount the Docker socket (root-equivalent on the host); the OpsMind API and dashboard have no authentication; Grafana allows anonymous viewing. Before any shared deployment: add auth, replace the socket with a narrowly-scoped agent, run Jenkins agents separately |

## 7. Failure handling matrix

| Failure | Behaviour | Tested in |
|---|---|---|
| No LLM key | rule engine | `test_workflow.py` |
| LLM rate limit / outage | next provider, then rule engine; attempts in trace | `test_diagnosis_llm.py` |
| Malformed LLM JSON | one corrective retry, then next provider | `test_diagnosis_llm.py` |
| LLM invents a runbook | replaced by the rule-engine choice | `test_diagnosis_llm.py` |
| Hindsight down | recall → "unavailable", retain → kept in DB | `test_workflow.py` |
| Prometheus down | tool error recorded as missing evidence | `test_workflow.py` |
| Slack down / unconfigured | log + continue; dashboard approval | `test_executor_slack_logs.py` |
| Dry run fails | abort before apply → REMEDIATION_FAILED | `test_workflow.py` |
| Execution timeout | reported with partial output | `test_executor_slack_logs.py` |
| Remediation doesn't help | REMEDIATION_FAILED from metrics | `test_workflow.py` |
| No traffic to verify | VERIFICATION_INCONCLUSIVE | `test_workflow.py` |
| Concurrent decisions | 409 for the second | `test_api.py`, `test_stores.py` |
| Unexpected exception | ERROR status + message in trace | `test_workflow.py` |
