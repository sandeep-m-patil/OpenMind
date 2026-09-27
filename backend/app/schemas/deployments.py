"""A deployment event (posted by Jenkins, or by the incident simulator for the demo story)."""
from pydantic import BaseModel, Field

from app.schemas.alerts import SERVICE_PATTERN


class DeploymentIn(BaseModel):
    service: str = Field(pattern=SERVICE_PATTERN)
    version: str = Field(min_length=1, max_length=64)
    commit_sha: str | None = Field(default=None, max_length=64)
    author: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    changes: list[str] = Field(default_factory=list, max_length=50)
    source: str = Field(default="api", max_length=32)
