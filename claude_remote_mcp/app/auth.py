"""Simpele bearer-token authenticatie voor alle gemounte MCP-endpoints.

/health blijft publiek (geen geheime data, handig voor monitoring/uptime-checks).
Alles daarbuiten vereist: Authorization: Bearer <GATEWAY_TOKEN>
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import GATEWAY_TOKEN

PUBLIC_PATHS = {"/health"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        if not GATEWAY_TOKEN:
            return JSONResponse(
                {"error": "gateway_token is niet ingesteld in de add-on opties"},
                status_code=500,
            )

        auth_header = request.headers.get("authorization", "")
        if auth_header != f"Bearer {GATEWAY_TOKEN}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)
