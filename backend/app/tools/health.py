"""get_service_health(): ask the service itself (GET /health)."""
import httpx

HEALTH_TIMEOUT_SECONDS = 5


def check_health(base_url: str, transport: httpx.BaseTransport | None = None) -> dict:
    with httpx.Client(base_url=base_url, timeout=HEALTH_TIMEOUT_SECONDS, transport=transport) as client:
        response = client.get("/health")
    body = response.json()
    data = body.get("data") or {}
    return {
        "http_status": response.status_code,
        "status": data.get("status", "unknown"),
        "components": data.get("components", {}),
    }
