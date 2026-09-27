# Setup (Windows 11 + Docker Desktop)

Step by step, from nothing to a running OpsMind. All commands are **PowerShell**, run from the project
folder (`...\Hyd3.0\OpsMind`). Full command reference: [TECH_STACK.md §7](../TECH_STACK.md#7-commands).

## 1. Prerequisites

| Tool | Check | Needed for |
|---|---|---|
| Docker Desktop (WSL2 backend), running | `docker --version` | everything |
| Python 3.11 | `python --version` | simulator, tests |
| Node 24 | `node --version` | only to develop the dashboard |
| ~8 GB free disk, 16 GB RAM recommended | | Hindsight image is 3.6 GB; Jenkins adds ~1 GB RAM |

## 2. Configure

```powershell
Copy-Item .env.example .env
```

The defaults work as-is. OpsMind uses host ports 8001, 5433, 6380, 9090, 9093, 3001, 8002, 3002, 8888,
9999 (and 8081 for Jenkins) because 8000/5432/6379/3000/8080 are often taken. If one is busy, change it
in `.env`. To find what holds a port:

```powershell
Get-NetTCPConnection -LocalPort 8002 -State Listen
```

## 3. Start

```powershell
docker compose up -d --build
docker compose ps
```

First start downloads images (~5 GB) and Hindsight downloads its embedding model — allow a few minutes.
Expected: 9 services `Up`; `product-api`, `redis`, `postgres` show `(healthy)`.

## 4. Verify

```powershell
curl.exe http://127.0.0.1:8001/health      # product-api: "status":"ok"
curl.exe http://127.0.0.1:8002/health      # OpsMind: prometheus up, hindsight up
```

Open the dashboard <http://127.0.0.1:3002> (empty list) and Grafana <http://127.0.0.1:3001>.

## 5. Simulator (one time)

```powershell
cd incident-simulator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 6. First incident

```powershell
.\.venv\Scripts\python.exe load_generator.py --duration 1200     # terminal 1 — leave running
```

Wait **2 minutes** (so OpsMind has a healthy baseline), then in terminal 2:

```powershell
.\.venv\Scripts\python.exe create_incident.py --type cache
```

Within ~60 s INC-1001 appears in the dashboard as *Pending approval*. Continue with
[demo.md](demo.md) §4.

## 7. Optional upgrades

| Upgrade | How |
|---|---|
| Gemini / Groq diagnosis | put `GEMINI_API_KEY` and/or `GROQ_API_KEY` in `.env` → `docker compose up -d --no-deps opsmind-backend` ([TECH_STACK §7.9](../TECH_STACK.md#79-enable-gemini--groq)) |
| Slack approvals | create the app from `infrastructure/slack/app-manifest.yml`, set the three `SLACK_*` values ([TECH_STACK §7.10](../TECH_STACK.md#710-enable-slack)) |
| Jenkins CI/CD | `docker compose --profile cicd up -d --build jenkins` → <http://127.0.0.1:8081> ([TECH_STACK §7.8](../TECH_STACK.md#78-jenkins)) |
| Hindsight fact extraction | `HINDSIGHT_LLM_PROVIDER=gemini`, `HINDSIGHT_LLM_API_KEY`, `HINDSIGHT_LLM_MODEL` → `docker compose up -d hindsight` |

## 8. Tests

See [TECH_STACK §7.6](../TECH_STACK.md#76-tests). Every suite enforces ≥ 80 % coverage.

## 9. Reset / stop

```powershell
cd incident-simulator; .\.venv\Scripts\python.exe reset_demo.py --yes   # clear incidents + memory
docker compose down        # stop (keeps data)
docker compose down -v     # stop and delete ALL data (databases, Hindsight memory, Jenkins)
```

## 10. Troubleshooting

See [TECH_STACK §8](../TECH_STACK.md#8-troubleshooting) — the most common ones:

- **No incident appears** → the load generator must be running (alerts need traffic).
- **"baseline of 800 ms"** → traffic started too recently; wait 2 minutes before injecting.
- **`hindsight: down`** right after first start → it's downloading its model; wait 1–2 minutes.
- Use **`127.0.0.1`**, not `localhost`, and **`curl.exe`**, not `curl`.
