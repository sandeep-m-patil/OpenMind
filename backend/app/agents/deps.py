"""Everything the graph nodes need, injected once (tests pass fakes)."""
from dataclasses import dataclass
from typing import Callable

from app.config import Settings
from app.services.deployment_store import DeploymentStore
from app.services.executor import AnsibleExecutor
from app.services.llm import LLMClient
from app.services.memory import MemoryService
from app.services.policy import PolicyGate
from app.services.runbooks import RunbookCatalog
from app.services.strategy_scores import StrategyScores
from app.tools.metrics import PrometheusClient


@dataclass
class AgentDeps:
    settings: Settings
    prometheus: PrometheusClient
    health_check: Callable[[], dict]
    read_logs: Callable[[int], dict]
    deployments: DeploymentStore
    memory: MemoryService
    llm: LLMClient
    catalog: RunbookCatalog
    policy: PolicyGate
    executor: AnsibleExecutor
    strategies: StrategyScores
    sleep: Callable[[float], None]
