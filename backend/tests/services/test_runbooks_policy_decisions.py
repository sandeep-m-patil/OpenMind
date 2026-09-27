import pytest

from app.schemas.decisions import DecisionIn
from app.services.decisions import DecisionError, resolve_decision
from app.services.policy import PolicyGate
from app.services.runbooks import InvalidRunbook, RunbookCatalog, validate_params
from app.services.strategy_scores import outcome_counters, proposal_counters, score
from tests.fakes import REPO

CATALOG = RunbookCatalog.load(str(REPO / "runbooks"))
POLICY = PolicyGate(CATALOG)
STATE = {"recommended_runbook": "RB-CACHE-002", "recommended_params": {}, "memory_guidance": {}}


def test_catalog_loads_all_four_runbooks():
    assert sorted(r.id for r in CATALOG.all()) == ["RB-CACHE-001", "RB-CACHE-002", "RB-DEPLOY-001", "RB-SERVICE-001"]


def test_defaults_are_filled_and_strings_coerced():
    assert validate_params(CATALOG.get("RB-CACHE-001"), {"max_idle_hours": "12"}) == {"max_idle_hours": 12}


@pytest.mark.parametrize("params", [{"max_idle_hours": 0}, {"max_idle_hours": True}, {"rm": "-rf"}])
def test_invalid_params_are_refused(params):
    with pytest.raises(InvalidRunbook):
        validate_params(CATALOG.get("RB-CACHE-001"), params)


def test_enum_parameters_are_allowlisted():
    with pytest.raises(InvalidRunbook):
        validate_params(CATALOG.get("RB-SERVICE-001"), {"service": "postgres"})


def test_unknown_runbook_is_refused_by_policy():
    assert POLICY.evaluate("RB-NOPE-001", {}, set()).is_allowed is False


def test_policy_raises_risk_of_previously_overruled_runbook():
    assert POLICY.evaluate("RB-CACHE-001", {}, {"RB-CACHE-001"}).risk == "MEDIUM"


def test_no_runbook_means_manual_investigation():
    assert POLICY.evaluate(None, {}, set()).is_allowed is False


def test_approval_takes_the_recommendation():
    resolved = resolve_decision(DecisionIn(decision="APPROVED", operator="a"), STATE, POLICY)

    assert resolved["final_action"]["runbook_id"] == "RB-CACHE-002"


def test_modification_of_params_only_keeps_runbook():
    state = {**STATE, "recommended_runbook": "RB-CACHE-001", "recommended_params": {"max_idle_hours": 24}}
    resolved = resolve_decision(DecisionIn(decision="MODIFIED", operator="a", params={"max_idle_hours": 48}), state, POLICY)

    assert resolved["final_action"] == {"runbook_id": "RB-CACHE-001", "params": {"max_idle_hours": 48}, "risk": "LOW"}


def test_rejection_has_no_final_action():
    assert resolve_decision(DecisionIn(decision="REJECTED", operator="a"), STATE, POLICY)["final_action"] is None


def test_approving_nothing_is_an_error():
    with pytest.raises(DecisionError):
        resolve_decision(DecisionIn(decision="APPROVED", operator="a"), {**STATE, "recommended_runbook": None}, POLICY)


def test_manual_execution_without_runbook_is_allowed():
    state = {**STATE, "recommended_runbook": None}

    assert resolve_decision(DecisionIn(decision="EXECUTE_MANUALLY", operator="a"), state, POLICY)["final_action"] is None


def test_modified_requires_a_change():
    with pytest.raises(ValueError):
        DecisionIn(decision="MODIFIED", operator="a")


def test_score_matches_spec_example():
    assert score({"proposed": 10, "approved": 9, "modified": 1, "succeeded": 9, "adopted": 0}) == 0.9


def test_score_is_unknown_without_attempts():
    assert score({}) is None


def test_adopted_runbook_gets_credit_for_success():
    assert outcome_counters("MODIFIED", "RB-CACHE-002", "RB-CACHE-001", "RESOLVED") == ["succeeded", "adopted"]


def test_manual_execution_is_not_scored():
    assert outcome_counters("EXECUTE_MANUALLY", "RB-CACHE-001", "RB-CACHE-001", "RESOLVED") == []


def test_proposal_counters_for_rejection():
    assert proposal_counters("REJECTED") == ["proposed", "rejected"]
