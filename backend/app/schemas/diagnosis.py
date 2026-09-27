"""Structured diagnosis the LLM (or the rule engine) must return. Validated before use."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["cache_saturation", "bad_deployment", "service_crash", "database_slowdown", "unknown"]


class DiagnosisOutput(BaseModel):
    root_cause: str = Field(min_length=3, max_length=300)
    category: Category
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    # Must be an ID from the runbook catalog (validated by the planner), or null for "no safe action".
    recommended_runbook: str | None = None
    runbook_params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=1200)
    historical_references: list[str] = Field(default_factory=list, max_length=5)
