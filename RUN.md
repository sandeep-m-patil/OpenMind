# How to Run OpsMind

The quickest path from nothing to the full demo. These commands work in **PowerShell** and in
**Git Bash**. Run them from the `OpsMind` folder unless a step says otherwise.

More detail: [TECH_STACK.md](TECH_STACK.md) (every command) · [docs/demo.md](docs/demo.md) (talking points).

---

## First time only

**1. Create your config file** (the defaults work as they are):

```bash
cp .env.example .env
```

**2. Start everything.** The first run downloads about 5 GB, so allow several minutes:

```bash
docker compose up -d --build
```

**3. Check it's running.** All 9 services should say `Up`:

```bash
docker compose ps
```

**4. Set up the simulator's Python environment:**

```bash
cd incident-simulator
```

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

---

## Run the demo (from inside `incident-simulator`)

**5. Start with an empty memory** (deletes previous incidents and learned memory):

```bash
.venv/Scripts/python.exe reset_demo.py --yes
```

**6. Start traffic in a second terminal and leave it running.** In the new terminal, `cd` into
`incident-simulator` first:

```bash
.venv/Scripts/python.exe load_generator.py --duration 1200
```

**7. Open the dashboards:**

| What | URL |
|---|---|
| OpsMind dashboard | <http://127.0.0.1:3002> |
| Grafana | <http://127.0.0.1:3001> |

**8. Wait 2 minutes** (so OpsMind sees a healthy baseline), **then break it — incident #1:**

```bash
.venv/Scripts/python.exe create_incident.py --type cache
```

**9. About 60 seconds later INC-1001 appears in the dashboard.** Open it, then:

1. Enter your name.
2. Click **Edit** and choose `RB-CACHE-001`.
3. Add the comment: *Only remove stale session keys*.
4. Click **Submit edited action**.
5. Wait until the status shows **Resolved**.

**10. When Grafana is green again, trigger the same incident — incident #2:**

```bash
.venv/Scripts/python.exe create_incident.py --type cache
```

**11. Open INC-1002.** It should now recommend `RB-CACHE-001` (LOW risk, 92%) and cite INC-1001.
Click **Approve**.

**12. Open the Learning page** at <http://127.0.0.1:3002/learning> to see the strategy scores and
search Hindsight's memory.

---

## Optional

**Jenkins.** Start it, then open <http://127.0.0.1:8081> (login `admin` / `changeme-local-only`):

```bash
docker compose --profile cicd up -d --build jenkins
```

**Gemini.** Put your key in `.env` as `GEMINI_API_KEY=...`, then restart the backend:

```bash
docker compose up -d --no-deps opsmind-backend
```

**Health check.** Shows the status of Prometheus, Hindsight, the LLM and Slack:

```bash
curl.exe http://127.0.0.1:8002/health
```

---

## Stop

Stops everything and keeps your data (run it from the `OpsMind` folder):

```bash
docker compose down
```

---

## If something looks wrong

| Problem | Fix |
|---|---|
| No incident appears | The traffic generator (step 6) must be running — alerts need traffic |
| Evidence says "baseline of 800 ms" | You injected too early — wait 2 minutes of traffic first |
| Incident is mild (P95 under 1 s) | Run `create_incident.py --type cache` again |
| `hindsight: down` right after first start | It's downloading its model — wait 1–2 minutes |
| Need a fresh start | `.venv/Scripts/python.exe reset_demo.py --yes` |

Full troubleshooting table: [TECH_STACK.md §8](TECH_STACK.md#8-troubleshooting).
