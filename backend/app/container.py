"""Builds every real dependency once at startup (tests build their own with fakes)."""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from slack_sdk.web import WebClient

from app.agents.deps import AgentDeps
from app.agents.graph import build_graph
from app.config import Settings
from app.db import apply_schema, ensure_database, open_pool
from app.schemas.decisions import DecisionIn
from app.services.deployment_store import DeploymentStore
from app.services.executor import AnsibleExecutor
from app.services.incident_store import IncidentStore
from app.services.llm import LLMClient, build_llm
from app.services.memory import MemoryService
from app.services.policy import PolicyGate
from app.services.runbooks import RunbookCatalog
from app.services.slack import NullNotifier, SlackNotifier, start_socket_mode
from app.services.strategy_scores import StrategyScores
from app.services.workflow import WorkflowRunner
from app.tools.health import check_health
from app.tools.logs import summarize_logs
from app.tools.metrics import PrometheusClient

logger = logging.getLogger("opsmind.container")


@dataclass
class Container:
    settings: Settings
    incidents: IncidentStore
    deployments: DeploymentStore
    strategies: StrategyScores
    memory: MemoryService
    catalog: RunbookCatalog
    llm: LLMClient
    prometheus: PrometheusClient
    runner: WorkflowRunner
    notifier: Any
    closers: list = field(default_factory=list)

    def close(self) -> None:
        self.runner.shutdown()
        for close in self.closers:
            close()


def _slack(settings: Settings, runner_ref: list) -> tuple[Any, list]:
    if not (settings.slack_bot_token and settings.slack_channel_id):
        return NullNotifier(), []
    client = WebClient(token=settings.slack_bot_token)
    notifier = SlackNotifier(client, settings.slack_channel_id, settings.dashboard_url)
    if not settings.slack_app_token:
        return notifier, []  # notifications only; approve via dashboard

    def decide(incident_id: str, decision: str, operator: str) -> None:
        runner_ref[0].decide(incident_id, DecisionIn(decision=decision, operator=operator, comment="via Slack"))

    try:
        socket = start_socket_mode(settings.slack_app_token, client, decide, notifier)
        return notifier, [socket.close]
    except Exception as exc:  # noqa: BLE001 — Slack must never stop OpsMind from starting
        logger.warning("slack socket mode failed", extra={"event": "slack_error", "error": str(exc)})
        return notifier, []


def build_container(settings: Settings) -> Container:
    ensure_database(settings.database_url)
    pool: ConnectionPool = open_pool(settings.database_url)
    apply_schema(pool)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    catalog = RunbookCatalog.load(settings.runbooks_dir)
    incidents, deployments, strategies = IncidentStore(pool), DeploymentStore(pool), StrategyScores(pool)
    memory = MemoryService(settings.hindsight_url, settings.hindsight_bank)
    prometheus, llm, policy = PrometheusClient(settings.prometheus_url), build_llm(settings), PolicyGate(catalog)
    deps = AgentDeps(
        settings=settings, prometheus=prometheus,
        health_check=lambda: check_health(settings.product_api_url),
        read_logs=lambda minutes: summarize_logs(settings.product_api_log_file, minutes),
        deployments=deployments, memory=memory, llm=llm, catalog=catalog, policy=policy,
        executor=AnsibleExecutor(settings.ansible_dir, settings.execution_timeout_seconds),
        strategies=strategies, sleep=time.sleep,
    )
    graph = build_graph(deps, checkpointer, lambda incident_id, state: incidents.save_state(incident_id, state, state.get("status")))
    runner_ref: list = []
    notifier, closers = _slack(settings, runner_ref)
    runner = WorkflowRunner(graph, incidents, policy, notifier, is_async=settings.is_background_enabled)
    runner_ref.append(runner)
    return Container(settings, incidents, deployments, strategies, memory, catalog, llm, prometheus,
                     runner, notifier, closers + [pool.close])
