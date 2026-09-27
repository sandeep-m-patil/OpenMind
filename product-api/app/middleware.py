"""Records metrics and a structured log line for every HTTP request."""
import logging
import time

from fastapi import Request

from app.metrics import ERRORS, LATENCY, REQUESTS

HTTP_INTERNAL_ERROR = 500
MS_PER_SECOND = 1000
# Scraped every few seconds; only log them when something is wrong.
QUIET_PATHS = {"/metrics", "/health"}
UNMATCHED_PATH = "unmatched"

logger = logging.getLogger("product_api.http")


def _route_template(request: Request) -> str:
    """'/products/{product_id}' rather than '/products/42' — keeps metric labels bounded."""
    route = request.scope.get("route")
    return getattr(route, "path", UNMATCHED_PATH)


class RequestObserver:
    def __init__(self, slow_request_ms: int) -> None:
        self._slow_request_ms = slow_request_ms

    async def __call__(self, request: Request, call_next):
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            self._record(request, response, time.perf_counter() - start)

    def _record(self, request: Request, response, elapsed_seconds: float) -> None:
        path = _route_template(request)
        status = response.status_code if response is not None else HTTP_INTERNAL_ERROR
        REQUESTS.labels(request.method, path, str(status)).inc()
        LATENCY.labels(request.method, path).observe(elapsed_seconds)
        if status >= HTTP_INTERNAL_ERROR:
            ERRORS.labels(request.method, path).inc()

        duration_ms = round(elapsed_seconds * MS_PER_SECOND, 1)
        is_slow = duration_ms >= self._slow_request_ms
        is_error = status >= HTTP_INTERNAL_ERROR
        if path in QUIET_PATHS and not (is_slow or is_error):
            return
        level = logging.WARNING if (is_slow or is_error) else logging.INFO
        logger.log(
            level,
            "slow request" if is_slow else "request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "route": path,
                "status": status,
                "duration_ms": duration_ms,
                "cache": response.headers.get("x-cache") if response is not None else None,
            },
        )
