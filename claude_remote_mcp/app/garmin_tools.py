"""MCP-tools voor Garmin Connect data (activiteiten, gezondheidscijfers, agenda).

Gebruikt de 'garminconnect' library. Bij de eerste login worden sessie-tokens
opgeslagen in een eigen map per account (persistent op /data), zodat niet elke
keer opnieuw ingelogd hoeft te worden.

Per Garmin-account bouwt maak_garmin_mcp() een eigen MCP-server met eigen login:
garmin_mcp (garmin_email) op /mcp/garmin/ en, als garmin_eline_email is
ingevuld, garmin_eline_mcp op /mcp/garmin-eline/.
"""

import json
from typing import Optional

import garminconnect
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from app.config import (
    GARMIN_ELINE_EMAIL,
    GARMIN_ELINE_PASSWORD,
    GARMIN_ELINE_TOKEN_DIR,
    GARMIN_EMAIL,
    GARMIN_PASSWORD,
    GARMIN_TOKEN_DIR,
)


class GarminAccount:
    """Eén Garmin-account: inloggegevens, sessiemap en de (lazy) ingelogde client."""

    def __init__(self, email: Optional[str], password: Optional[str], token_dir: str, optie: str):
        self.email = email
        self.password = password
        self.token_dir = token_dir
        self.optie = optie  # naam van de add-on opties, voor de foutmelding
        self.client: Optional[garminconnect.Garmin] = None

    def get_client(self) -> garminconnect.Garmin:
        """Geeft een ingelogde Garmin-client terug (lazy init, hergebruikt sessie)."""
        if self.client is not None:
            return self.client

        client = garminconnect.Garmin(email=self.email, password=self.password)
        try:
            client.login(tokenstore=self.token_dir)
        except garminconnect.GarminConnectAuthenticationError as e:
            raise RuntimeError(
                f"Kon niet inloggen bij Garmin Connect. Controleer {self.optie}_email en "
                f"{self.optie}_password in de add-on opties. "
                f"Onderliggende fout: {e}"
            ) from e

        self.client = client
        return self.client


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


class MonthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(..., ge=2000, le=2100, description="Jaar, bv. 2026")
    month: int = Field(..., ge=1, le=12, description="Maand 1-12 (1 = januari)")


class WorkoutIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workout_id: str = Field(..., description="Garmin workout ID (zie garmin_get_calendar)")


def maak_garmin_mcp(naam: str, account: GarminAccount) -> MCPServer:
    """Bouwt de MCP-server met alle Garmin-tools voor één account."""
    garmin_mcp = MCPServer(naam)
    _get_client = account.get_client


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


    @garmin_mcp.tool(
        name="garmin_get_fitness_age",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    async def garmin_get_fitness_age(params: DateInput) -> str:
        """Haal de fitnessleeftijd van een datum op.

        Args:
            params: date in YYYY-MM-DD formaat

        Returns:
            JSON met fitnessleeftijd, echte leeftijd, haalbare fitnessleeftijd en de onderdelen
            (VO2 max, rustpols, BMI/vetpercentage, intensieve minuten).
        """
        try:
            client = _get_client()
            data = client.get_fitnessage_data(params.date)
            return json.dumps(data, indent=2, default=str)
        except Exception as e:
            return _error(e)

    @garmin_mcp.tool(
        name="garmin_get_calendar",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    async def garmin_get_calendar(params: MonthInput) -> str:
        """Haal de Garmin Connect-agenda van een maand op: geplande workouts (ook uit een
        trainingsplan of Garmin Coach), activiteiten en evenementen.

        Args:
            params: year en month (1-12)

        Returns:
            JSON met calendarItems (o.a. itemType, title, date, workoutId, duration, distance).
        """
        try:
            client = _get_client()
            data = client.get_scheduled_workouts(params.year, params.month)
            return json.dumps(data, indent=2, default=str)
        except Exception as e:
            return _error(e)

    @garmin_mcp.tool(
        name="garmin_get_workout",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    async def garmin_get_workout(params: WorkoutIdInput) -> str:
        """Haal de details van een workout op: stappen, doelen (tempo, hartslag, duur).

        Args:
            params: workout_id, te vinden via garmin_get_calendar

        Returns:
            JSON met de workout en zijn stappen.
        """
        try:
            client = _get_client()
            data = client.get_workout_by_id(params.workout_id)
            return json.dumps(data, indent=2, default=str)
        except Exception as e:
            return _error(e)

    return garmin_mcp


# Jelle: /mcp/garmin/ (de bestaande connector). Eline: /mcp/garmin-eline/, alleen als ingevuld.
garmin_mcp = maak_garmin_mcp("garmin_mcp", GarminAccount(GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_TOKEN_DIR, "garmin"))
garmin_eline_mcp: Optional[MCPServer] = (
    maak_garmin_mcp(
        "garmin_eline_mcp",
        GarminAccount(GARMIN_ELINE_EMAIL, GARMIN_ELINE_PASSWORD, GARMIN_ELINE_TOKEN_DIR, "garmin_eline"),
    )
    if GARMIN_ELINE_EMAIL
    else None
)
