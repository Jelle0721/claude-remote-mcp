"""Simpele token-authenticatie voor alle gemounte MCP-endpoints.

/health blijft publiek (geen geheime data, handig voor monitoring/uptime-checks).

Alles daarbuiten accepteert het token op twee manieren:
  1. Header: Authorization: Bearer <GATEWAY_TOKEN>
  2. Query-param: ?token=<GATEWAY_TOKEN>  (nodig omdat Claude's custom-connector
     UI geen los headerveld biedt - je geeft alleen een URL op)

We geven bij een ontbrekend/fout token bewust een 403 terug, geen 401: een 401
op een MCP-endpoint laat Claude's client automatisch een OAuth-inlogflow
proberen te starten (die wij niet hebben geimplementeerd), wat verwarrende
"kon niet inloggen"-meldingen oplevert. Een 403 triggert dat gedrag niet.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import GATEWAY_TOKEN

PUBLIC_PATHS = {"/health", "/bank/callback"}


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
        query_token = request.query_params.get("token", "")

        if auth_header == f"Bearer {GATEWAY_TOKEN}" or query_token == GATEWAY_TOKEN:
            return await call_next(request)

        return JSONResponse({"error": "Forbidden"}, status_code=403)
