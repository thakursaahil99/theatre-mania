from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF defence for cookie-authenticated endpoints.

    Browsers always send `Origin` on cross-site unsafe requests; we reject any that are
    not explicitly allowed. Non-browser clients (no Origin, Bearer auth) are unaffected.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin != "null":
                allowed = set(settings.cors_origins) | {_origin(settings.FRONTEND_URL), _origin(str(request.base_url))}
                if origin.rstrip("/") not in allowed:
                    return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if settings.ENV == "prod":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
