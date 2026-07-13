"""Security response headers for an API origin.

The CSP is deliberately maximal (`default-src 'none'`) because this service
serves JSON, not HTML. HSTS is only emitted in production where TLS is
guaranteed by the edge (Traefik), so local HTTP development isn't poisoned.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, enable_hsts: bool) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        headers.setdefault("Cache-Control", "no-store")
        if self._enable_hsts:
            headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
            )
        return response
