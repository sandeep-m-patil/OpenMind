# Demo Script

The final demo story (built up phase by phase):

1. Developer deploys a change → Jenkins deploys product-api.
2. Latency spikes (P95 150 ms → 4.8 s); Redis memory 96%, evictions climbing.
3. Prometheus alert fires → OpsMind opens an incident.
4. OpsMind collects logs, metrics, recent deployments; **recalls similar incidents from Hindsight**.
5. Diagnosis + confidence + evidence; proposes a pre-approved runbook with a risk rating.
6. Slack message → engineer **edits**: "don't flush the whole cache — only stale session keys".
7. Approved runbook runs via Ansible; OpsMind verifies recovery from real metrics (4.8 s → 180 ms).
8. Postmortem + lesson retained in Hindsight.
9. **Same incident again** → OpsMind recalls the human correction and recommends targeted cleanup first.
10. Show before/after: the recommendation changed because of memory.

## What you can demo today (Phases 1–2)

From `incident-simulator\` (see [setup.md](setup.md) §5 for the one-time venv):

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py load_generator.py --duration 20                    # 1. healthy: p95 ~13 ms, 100% hits
& $py create_incident.py --type cache                    # 2. inject: Redis 100%, ~19k TTL-less sessions
& $py load_generator.py --duration 20 --no-warmup        # 3. incident: p95 ~5–7 s, ~5% hits
docker compose logs product-api --tail 5                 #    'cache write rejected ... maxmemory'
& $py create_incident.py --type cache --status           # 4. 300 active vs ~19k stale sessions
& $py create_incident.py --type cache --restore          # 5. reset
& $py load_generator.py --duration 20                    # 6. recovered: p95 ~13–20 ms
```

Talking points:
- *"A bad auth-service deploy dropped the TTL on sessions. Redis may only evict keys with a TTL — so it
  evicted our product cache instead. Every request now pays a 250 ms query; traffic keeps arriving at
  50 req/s but we can only serve ~40, so a queue forms and latency explodes."*
- *"Note step 4: 300 of those sessions belong to users active right now. 'Flush the cache' would fix
  latency and log them all out. Remember that — it's the correction the operator will teach OpsMind."*
