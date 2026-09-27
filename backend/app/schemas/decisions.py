"""A human's decision on an AI recommendation."""
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Decision = Literal["APPROVED", "MODIFIED", "REJECTED", "EXECUTE_MANUALLY"]
RUNBOOK_ID_PATTERN = r"^RB-[A-Z]+-\d{3}$"


class DecisionIn(BaseModel):
    decision: Decision
    operator: str = Field(min_length=1, max_length=80)
    comment: str = Field(default="", max_length=1000)
    # Only for MODIFIED: the runbook (and/or parameters) the human wants instead.
    runbook_id: str | None = Field(default=None, pattern=RUNBOOK_ID_PATTERN)
    params: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _modified_needs_a_change(self) -> "DecisionIn":
        if self.decision == "MODIFIED" and self.runbook_id is None and self.params is None:
            raise ValueError("MODIFIED requires runbook_id and/or params")
        return self
