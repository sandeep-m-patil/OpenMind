"""Incoming alerts: Alertmanager webhook payload, or a manual trigger."""
from typing import Literal

from pydantic import BaseModel, Field

SERVICE_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"
Severity = Literal["critical", "warning", "info"]


class AlertmanagerAlert(BaseModel):
    status: Literal["firing", "resolved"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    fingerprint: str | None = None


class AlertmanagerWebhook(BaseModel):
    """Subset of https://prometheus.io/docs/alerting/latest/configuration/#webhook_config"""

    status: Literal["firing", "resolved"]
    alerts: list[AlertmanagerAlert] = Field(max_length=100)


class ManualIncidentIn(BaseModel):
    service: str = Field(default="product-api", pattern=SERVICE_PATTERN)
    title: str = Field(default="High latency", min_length=3, max_length=200)
    severity: Severity = "critical"
    symptoms: list[str] = Field(default_factory=list, max_length=20)
