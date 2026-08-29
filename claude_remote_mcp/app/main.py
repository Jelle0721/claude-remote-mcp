"""Claude Remote MCP Gateway.

Draait permanent op de Home Assistant Green als add-on en stelt twee
MCP-servers bloot via Streamable HTTP:

  /mcp/garmin/          - Garmin Connect data
  /mcp/homeassistant/   - Home Assistant automations etc. (via HA Vibecode Agent)

Beveiligd met een gedeeld bearer-token (gateway_token add-on optie).
Voeg deze URL toe als custom/remote connector in Claude's connector-instellingen
(via een publieke HTTPS-tunnel, bv. Cloudflare Tunnel, wijzend naar poort 8300).
"""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.auth import BearerAuthMiddleware
from app.config import GATEWAY_TOKEN, HA_AGENT_URL, LOG_LEVEL, PORT
from app.garmin_tools import garmin_mcp
from app.ha_tools import homeassistant_mcp

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("claude_remote_mcp")


async def health(request):
    return JSONResponse({"status": "ok", "ha_agent_url": HA_AGENT_URL})


def build_app() -> Starlette:
    if not GATEWAY_TOKEN:
        logger.warning(
            "gateway_token is niet ingesteld! Stel deze in via de add-on opties "
            "voordat je deze server publiek bereikbaar maakt."
        )

    # host="0.0.0.0" omdat we in een container draaien en op alle interfaces
    # moeten luisteren. Dit voorkomt ook dat de ingebouwde DNS-rebinding-
    # bescherming van de MCP SDK verkeerde Host-headers afwijst achter een
    # tunnel/reverse proxy met een eigen domeinnaam - de bearer-token-check
    # hierboven is hier de primaire beveiligingslaag.
    garmin_app = garmin_mcp.streamable_http_app(streamable_http_path="/", host="0.0.0.0")
    ha_app = homeassistant_mcp.streamable_http_app(streamable_http_path="/", host="0.0.0.0")

    @asynccontextmanager
    async def combined_lifespan(app):
        # Mount() geeft ASGI-lifespan events niet automatisch door aan de
        # submounts, dus we starten/sluiten hun sessiemanagers hier expliciet.
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(garmin_app.router.lifespan_context(garmin_app))
            await stack.enter_async_context(ha_app.router.lifespan_context(ha_app))
            logger.info("Claude Remote MCP Gateway gestart op poort %s", PORT)
            yield

    app = Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp/garmin", app=garmin_app),
            Mount("/mcp/homeassistant", app=ha_app),
        ],
        lifespan=combined_lifespan,
    )
    app.add_middleware(BearerAuthMiddleware)
    return app


app = build_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level=LOG_LEVEL.lower())
