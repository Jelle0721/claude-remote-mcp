"""MCP-tools die doorverbinden met de HA Vibecode Agent (draait als add-on op
dezelfde Home Assistant instantie).

Ontwerpkeuze: in plaats van elk Agent-endpoint hier hard te coderen (en zo
stil te breken zodra de Agent update), bieden we:

  1. ha_list_endpoints - haalt het LIVE OpenAPI-schema van de Agent op, dus
     Claude weet altijd exact welke paden/methodes/parameters beschikbaar zijn.
  2. ha_call_api        - generieke, geauthenticeerde proxy naar elk endpoint.

Dit geeft volledige dekking (automations, scripts, entities, helpers,
dashboards, thema's, HACS, logs, back-ups/rollback) zonder aannames over
exacte padnamen die kunnen wijzigen.
"""

import json
from typing import Optional

import httpx
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from app.config import HA_AGENT_KEY, HA_AGENT_URL

homeassistant_mcp = MCPServer("home_assistant_mcp")


def _headers() -> dict:
    return {"Authorization": f"Bearer {HA_AGENT_KEY}"} if HA_AGENT_KEY else {}


@homeassistant_mcp.tool(
    name="ha_list_endpoints",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def ha_list_endpoints() -> str:
    """Haal het live overzicht van alle beschikbare endpoints van de HA Vibecode
    Agent op (automations, scripts, entities, helpers, dashboards, thema's,
    HACS, logs, back-ups).

    Roep dit ALTIJD eerst aan voordat je ha_call_api gebruikt, zodat je het
    juiste pad, de juiste HTTP-methode en het verwachte request-schema weet.

    Returns:
        JSON-lijst met per endpoint: method, path, summary, parameters, has_body.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{HA_AGENT_URL}/openapi.json", headers=_headers())
            resp.raise_for_status()
            spec = resp.json()

        endpoints = []
        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                endpoints.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "summary": op.get("summary") or op.get("description", ""),
                        "parameters": [p.get("name") for p in op.get("parameters", [])],
                        "has_body": "requestBody" in op,
                    }
                )
        return json.dumps(endpoints, indent=2)
    except Exception as e:
        return json.dumps(
            {"error": f"Kon endpoints niet ophalen bij {HA_AGENT_URL}: {type(e).__name__}: {e}"}
        )


class CallApiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str = Field(..., description="HTTP-methode: GET, POST, PUT, PATCH of DELETE")
    path: str = Field(
        ..., description="API-pad zoals teruggegeven door ha_list_endpoints, bv. '/api/automations'"
    )
    json_body: Optional[dict] = Field(
        default=None, description="Request body als JSON-object, indien van toepassing"
    )
    query_params: Optional[dict] = Field(
        default=None, description="Query-parameters als key-value paren"
    )


@homeassistant_mcp.tool(
    name="ha_call_api",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
)
async def ha_call_api(params: CallApiInput) -> str:
    """Voer een aanroep uit tegen de HA Vibecode Agent REST API - het werkpaard
    voor alle Home Assistant taken: automations aanmaken/wijzigen/verwijderen,
    scripts, helpers, dashboards, thema's, HACS-integraties, logs en
    back-ups/rollback.

    Gebruik EERST ha_list_endpoints om het juiste pad en schema te bepalen.
    De Agent zet automatisch een Git-commit voor elke wijziging, dus fouten
    zijn terug te draaien via het rollback-endpoint.

    Args:
        params: method (GET/POST/PUT/PATCH/DELETE), path, optioneel json_body
            en query_params

    Returns:
        JSON met status en data van de Agent, of een foutmelding met statuscode.
    """
    method = params.method.upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return json.dumps({"error": f"Ongeldige HTTP-methode: {method}"})

    try:
        # 120s i.p.v. 30s: sommige Agent-acties (bv. een dashboard toepassen)
        # doen intern een git-commit + backup + configuratie-herlaad en duren
        # structureel 40-45 seconden. Met 30s liep dat spuriieus op een timeout
        # terwijl de actie server-side gewoon slaagde.
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.request(
                method,
                f"{HA_AGENT_URL}{params.path}",
                headers=_headers(),
                json=params.json_body,
                params=params.query_params,
            )
        try:
            body = resp.json()
        except ValueError:
            body = resp.text

        if resp.status_code >= 400:
            return json.dumps({"status": resp.status_code, "error": body}, default=str)
        return json.dumps({"status": resp.status_code, "data": body}, default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
