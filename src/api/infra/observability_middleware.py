"""Application-level HTTP instrumentation."""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.infra.metrics import HTTP_ERRORS, HTTP_LATENCY, HTTP_REQUESTS


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Emit Prometheus HTTP metrics for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Measure a response using its route template rather than the raw URL path."""
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        endpoint = route.path if route else "unmatched"
        duration = time.perf_counter() - started
        labels = {
            "method": request.method,
            "endpoint": endpoint,
            "status_code": str(response.status_code),
        }
        HTTP_REQUESTS.labels(**labels).inc()
        HTTP_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
        if response.status_code >= 400:
            HTTP_ERRORS.labels(**labels).inc()
        return response
