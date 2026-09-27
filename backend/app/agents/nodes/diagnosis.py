"""Node 4 — Diagnosis: one structured LLM call (diagnosis + runbook choice); rule engine as fallback."""
from app.agents import rules
from app.agents.deps import AgentDeps
from app.agents.prompts import SYSTEM_PROMPT, build_user_prompt
from app.agents.state import IncidentState, trace
from app.schemas.diagnosis import DiagnosisOutput
from app.services.llm import LLMError

PERCENT = 100


def make_diagnosis(deps: AgentDeps):
    def diagnosis(state: IncidentState) -> dict:
        scores = deps.strategies.all()
        catalog = [r.summary() for r in deps.catalog.all()]
        engine: dict = {"engine": "rules", "attempts": []}
        status = "ok"
        if deps.llm.is_configured:
            try:
                result = deps.llm.generate(SYSTEM_PROMPT, build_user_prompt(state, catalog, scores), DiagnosisOutput)
                output = result.output
                engine = {"engine": "llm", "provider": result.provider, "model": result.model, "attempts": result.attempts}
            except LLMError as exc:
                output = rules.diagnose(state.get("signals", {}), state.get("findings", []), state.get("memory_guidance", {}))
                engine = {"engine": "rules", "fallback_reason": str(exc), "attempts": str(exc).split("; ")}
                status = "warning"
        else:
            output = rules.diagnose(state.get("signals", {}), state.get("findings", []), state.get("memory_guidance", {}))
        who = f"{engine['provider']}/{engine['model']}" if engine["engine"] == "llm" else "rule engine"
        details = [f"Engine: {who}"] + output.evidence + ([output.rationale] if output.rationale else [])
        if engine.get("fallback_reason"):
            details.insert(1, f"LLM unavailable, fell back to rules: {engine['fallback_reason']}")
        return {
            "diagnosis": output.model_dump(), "confidence": output.confidence, "evidence": output.evidence,
            "diagnosis_engine": engine, "strategy_scores": scores,
            "trace": trace("diagnosis", f"Diagnosis: {output.category} — {output.root_cause} "
                           f"(confidence {output.confidence * PERCENT:.0f}%)", details, status),
        }

    return diagnosis
