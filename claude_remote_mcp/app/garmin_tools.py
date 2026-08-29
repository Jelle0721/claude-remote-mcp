"""MCP-tools voor Garmin Connect data (activiteiten, gezondheidscijfers).

Gebruikt de 'garminconnect' library. Bij de eerste login worden sessie-tokens
opgeslagen in GARMIN_TOKEN_DIR (persistent op /data), zodat niet elke keer
opnieuw ingelogd hoeft te worden.
"""

import json
from typing import Optional

import garminconnect
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from app.config import GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_TOKEN_DIR

garmin_mcp = MCPServer("garmin_mcp")

_client: Optional[garminconnect.Garmin] = None


def _get_client() -> garminconnect.Garmin:
    """Geeft een ingelogde Garmin-client terug (lazy init, hergebruikt sessie)."""
    global _client
    if _client is not None:
        return _client

    client = garminconnect.Garmin(email=GARMIN_EMAIL, password=GARMIN_PASSWORD)
    try:
        client.login(tokenstore=GARMIN_TOKEN_DIR)
    except garminconnect.GarminConnectAuthenticationError as e:
        raise RuntimeError(
            "Kon niet inloggen bij Garmin Connect. Controleer garmin_email en "
            "garmin_password in de add-on opties. "
            f"Onderliggende fout: {e}"
        ) from e

    _client = client
    return _client


def _error(e: Exception) -> str:
    return json.dumps({"error": f"{type(e).__name__}: {e}"})


class DateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date: str = Field(..., description="Datum in YYYY-MM-DD formaat, bv. '2026-08-27'")


class DateRangeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    start_date: str = Field(..., description="Startdatum in YYYY-MM-DD formaat")
    end_date: str = Field(..., description="Einddatum in YYYY-MM-DD formaat")


class ListActivitiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum aantal activiteiten")
    start: int = Field(default=0, ge=0, description="Offset voor paginering")


class ActivityIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_id: str = Field(..., description="Garmin activity ID (zie garmin_list_activities)")


@garmin_mcp.tool(
    name="garmin_list_activities",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_list_activities(params: ListActivitiesInput) -> str:
    """Haal een lijst met recente Garmin Connect-activiteiten op.

    Args:
        params: limit (max aantal, 1-100) en start (offset voor paginering)

    Returns:
        JSON-lijst met activiteiten: id, naam, type, datum, afstand, duur, calorieen.
    """
    try:
        client = _get_client()
        activities = client.get_activities(params.start, params.limit)
        return json.dumps(activities, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_activity",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_activity(params: ActivityIdInput) -> str:
    """Haal gedetailleerde informatie over een specifieke activiteit op.

    Args:
        params: activity_id, te vinden via garmin_list_activities

    Returns:
        JSON met details: hartslagzones, tempo, hoogtemeters, splits.
    """
    try:
        client = _get_client()
        details = client.get_activity_details(params.activity_id)
        return json.dumps(details, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_daily_stats",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_daily_stats(params: DateInput) -> str:
    """Haal de dagstatistieken van een datum op: stappen, calorieen, verdiepingen, rustpols.

    Args:
        params: date in YYYY-MM-DD formaat

    Returns:
        JSON met samengevatte dagcijfers.
    """
    try:
        client = _get_client()
        stats = client.get_stats(params.date)
        return json.dumps(stats, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_heart_rate",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_heart_rate(params: DateInput) -> str:
    """Haal hartslagmetingen (inclusief rustpols) van een specifieke dag op.

    Args:
        params: date in YYYY-MM-DD formaat

    Returns:
        JSON met hartslagwaarden over de dag.
    """
    try:
        client = _get_client()
        hr = client.get_heart_rates(params.date)
        return json.dumps(hr, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_sleep",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_sleep(params: DateInput) -> str:
    """Haal slaapdata op: slaapfases, duur, slaapscore.

    Args:
        params: date in YYYY-MM-DD formaat (de ochtend na de nacht in kwestie)

    Returns:
        JSON met slaapfases en -statistieken.
    """
    try:
        client = _get_client()
        sleep = client.get_sleep_data(params.date)
        return json.dumps(sleep, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_body_composition",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_body_composition(params: DateRangeInput) -> str:
    """Haal lichaamssamenstelling op (gewicht, vetpercentage, spiermassa) over een periode.

    Args:
        params: start_date en end_date in YYYY-MM-DD formaat

    Returns:
        JSON met metingen per dag in de opgegeven periode.
    """
    try:
        client = _get_client()
        data = client.get_body_composition(params.start_date, params.end_date)
        return json.dumps(data, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_training_readiness",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_training_readiness(params: DateInput) -> str:
    """Haal de trainingsgereedheid-score en onderliggende factoren van een dag op.

    Args:
        params: date in YYYY-MM-DD formaat

    Returns:
        JSON met readiness-score, hersteltijd, slaapscore en HRV-status.
    """
    try:
        client = _get_client()
        readiness = client.get_training_readiness(params.date)
        return json.dumps(readiness, indent=2, default=str)
    except Exception as e:
        return _error(e)


@garmin_mcp.tool(
    name="garmin_get_body_battery",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def garmin_get_body_battery(params: DateRangeInput) -> str:
    """Haal Body Battery-energieniveaus op over een periode.

    Args:
        params: start_date en end_date in YYYY-MM-DD formaat

    Returns:
        JSON-lijst met Body Battery-waarden per dag.
    """
    try:
        client = _get_client()
        data = client.get_body_battery(params.start_date, params.end_date)
        return json.dumps(data, indent=2, default=str)
    except Exception as e:
        return _error(e)
