"""The OpsMind incident workflow as a LangGraph StateGraph.

    intake → evidence → recall → diagnosis → planner → approval ⏸
        approval ─APPROVED/MODIFIED→ execution ─ok→ verification → learning → END
                 ─EXECUTE_MANUALLY──────────────→ verification
                 ─REJECTED────────────────────────────────────→ learning
        execution ─failed→ learning

Every node's output is persisted to the incidents table as it completes, so the dashboard shows
progress live. The checkpointer lets the graph pause at `approval` for as long as the human needs.
"""
from typing import Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents.deps import AgentDeps
from app.agents.nodes.approval import make_approval, route_after_approval
from app.agents.nodes.diagnosis import make_diagnosis
from app.agents.nodes.evidence import make_evidence
from app.agents.nodes.execution import make_execution, route_after_execution
from app.agents.nodes.intake import make_intake
from app.agents.nodes.learning import make_learning
from app.agents.nodes.planner import make_planner
from app.agents.nodes.recall import make_recall
from app.agents.nodes.verification import make_verification
from app.agents.state import IncidentState

NODES = {
    "intake": make_intake,
    "evidence": make_evidence,
    "recall": make_recall,
    "diagnosis": make_diagnosis,
    "planner": make_planner,
    "approval": make_approval,
    "execution": make_execution,
    "verification": make_verification,
    "learning": make_learning,
}
LINEAR_EDGES = [(START, "intake"), ("intake", "evidence"), ("evidence", "recall"), ("recall", "diagnosis"),
                ("diagnosis", "planner"), ("planner", "approval"), ("verification", "learning"), ("learning", END)]

SaveSnapshot = Callable[[str, dict], None]


def _persisting(node: Callable, save: SaveSnapshot) -> Callable:
    def wrapped(state: IncidentState) -> dict:
        update = node(state)
        merged = {**state, **update, "trace": list(state.get("trace", [])) + list(update.get("trace", []))}
        save(state["incident_id"], merged)
        return update

    return wrapped


def build_graph(deps: AgentDeps, checkpointer: BaseCheckpointSaver, save: SaveSnapshot):
    graph = StateGraph(IncidentState)
    for name, factory in NODES.items():
        graph.add_node(name, _persisting(factory(deps), save))
    for source, target in LINEAR_EDGES:
        graph.add_edge(source, target)
    graph.add_conditional_edges("approval", route_after_approval, ["execution", "verification", "learning"])
    graph.add_conditional_edges("execution", route_after_execution, ["verification", "learning"])
    return graph.compile(checkpointer=checkpointer)
