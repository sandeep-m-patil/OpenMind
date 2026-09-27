"""POST /v1/alerts/prometheus — Alertmanager webhook. Critical firing alerts open incidents."""
from fastapi import APIRouter, Request

from app.api.envelope import container, envelope
from app.schemas.alerts import AlertmanagerWebhook

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])
OPENING_SEVERITY = "critical"


@router.post("/prometheus")
def prometheus_webhook(payload: AlertmanagerWebhook, request: Request):
    runner = container(request).runner
    opened, absorbed, ignored = [], [], 0
    for alert in payload.alerts:
        labels = alert.labels
        if alert.status != "firing" or labels.get("severity") != OPENING_SEVERITY:
            ignored += 1
            continue
        incident_id, is_new = runner.open_incident(
            service=labels.get("service", "unknown"),
            severity=labels["severity"],
            title=alert.annotations.get("summary") or labels.get("alertname", "alert"),
            alert=alert.model_dump(),
        )
        (opened if is_new else absorbed).append(incident_id)
    return envelope({"opened": opened, "absorbed": absorbed, "ignored": ignored})
