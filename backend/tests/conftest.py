from dataclasses import dataclass

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.deps import AgentDeps
from app.agents.graph import build_graph
from app.services.llm import LLMClient
from app.services.policy import PolicyGate
from app.services.runbooks import RunbookCatalog
from app.services.workflow import WorkflowRunner
from tests.fakes import (
    INCIDENT_LOGS,
    FakeDeployments,
    FakeExecutor,
    FakeIncidentStore,
    FakeMemory,
    FakePrometheus,
    FakeStrategies,
    RecordingNotifier,
    make_settings,
)


@dataclass
class Env:
    settings: object
    prometheus: FakePrometheus
    memory: FakeMemory
    executor: FakeExecutor
    strategies: FakeStrategies
    deployments: FakeDeployments
    incidents: FakeIncidentStore
    notifier: RecordingNotifier
    catalog: RunbookCatalog
    runner: WorkflowRunner
    health: dict
    llm: LLMClient

    def close(self) -> None:
        pass


def build_env(llm: LLMClient | None = None) -> Env:
    settings = make_settings()
    prometheus = FakePrometheus()
    memory, executor = FakeMemory(), FakeExecutor(prometheus)
    strategies, deployments, incidents = FakeStrategies(), FakeDeployments(), FakeIncidentStore()
    notifier, catalog = RecordingNotifier(), RunbookCatalog.load(settings.runbooks_dir)
    health = {"status": "ok", "http_status": 200, "components": {}}
    llm = llm or LLMClient([])
    policy = PolicyGate(catalog)
    deps = AgentDeps(settings=settings, prometheus=prometheus, health_check=lambda: health,
                     read_logs=lambda minutes: INCIDENT_LOGS, deployments=deployments, memory=memory, llm=llm,
                     catalog=catalog, policy=policy, executor=executor, strategies=strategies, sleep=lambda s: None)
    graph = build_graph(deps, InMemorySaver(), lambda i, s: incidents.save_state(i, s, s.get("status")))
    runner = WorkflowRunner(graph, incidents, policy, notifier, is_async=False)
    return Env(settings, prometheus, memory, executor, strategies, deployments, incidents, notifier, catalog,
               runner, health, llm)


@pytest.fixture
def env() -> Env:
    return build_env()
