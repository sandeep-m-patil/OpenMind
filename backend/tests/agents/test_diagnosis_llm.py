"""The diagnosis node with an LLM configured: valid output is used; failures fall back to rules."""
import json

from app.schemas.decisions import DecisionIn
from app.schemas.diagnosis import DiagnosisOutput
from app.services.llm import LLMClient, LLMError, LLMResult
from tests.conftest import build_env

VALID = {"root_cause": "Redis full of sessions", "category": "cache_saturation", "confidence": 0.9,
         "evidence": ["Redis 100%"], "recommended_runbook": "RB-CACHE-001", "runbook_params": {"max_idle_hours": 12},
         "rationale": "sessions", "historical_references": []}


class ScriptedProvider:
    name, model = "fake", "fake-1"

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)

    def complete_json(self, system: str, user: str) -> str:
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _state(llm):
    env = build_env(llm)
    incident_id, _ = env.runner.open_incident(service="product-api", severity="critical", title="High latency")
    return env, env.incidents.get(incident_id)["state"]


def test_llm_choice_and_params_are_used_when_valid():
    _, state = _state(LLMClient([ScriptedProvider([json.dumps(VALID)])]))

    assert (state["recommended_runbook"], state["recommended_params"], state["diagnosis_engine"]["engine"]) == (
        "RB-CACHE-001", {"max_idle_hours": 12}, "llm")


def test_malformed_output_gets_one_corrective_retry():
    _, state = _state(LLMClient([ScriptedProvider(["not json", "```json\n" + json.dumps(VALID) + "\n```"])]))

    assert state["diagnosis_engine"]["attempts"][0].startswith("fake: malformed output")


def test_llm_outage_falls_back_to_rule_engine():
    _, state = _state(LLMClient([ScriptedProvider([LLMError("rate limited")])]))

    assert (state["diagnosis_engine"]["engine"], state["recommended_runbook"]) == ("rules", "RB-CACHE-002")


def test_invented_runbook_is_replaced_by_a_catalog_runbook():
    _, state = _state(LLMClient([ScriptedProvider([json.dumps({**VALID, "recommended_runbook": "RB-RM-RF-999"})])]))

    assert state["recommended_runbook"] == "RB-CACHE-002"


def test_out_of_bounds_llm_params_fall_back_to_defaults():
    _, state = _state(LLMClient([ScriptedProvider([json.dumps({**VALID, "runbook_params": {"max_idle_hours": 0}})])]))

    assert state["recommended_params"] == {"max_idle_hours": 24}


def test_generate_reports_every_attempt_when_all_fail():
    llm = LLMClient([ScriptedProvider([LLMError("a")]), ScriptedProvider(["{}", "{}"])])

    try:
        llm.generate("s", "u", DecisionIn)
    except LLMError as exc:
        message = str(exc)
    assert message.count("fake:") == 3


def test_result_carries_provider_details():
    result = LLMClient([ScriptedProvider([json.dumps(VALID)])]).generate("s", "u", DiagnosisOutput)

    assert isinstance(result, LLMResult) and result.provider == "fake"
