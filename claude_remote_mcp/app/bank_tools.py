"""MCP-tools voor bankdata via Enable Banking (PSD2-koppeling met ING).

Beveiligingsprincipe: de private key komt NOOIT via Claude binnen. Jij vult 'm
zelf rechtstreeks in de add-on configuratie in Home Assistant in (als
base64-tekst, zie README), precies zoals gateway_token en ha_agent_key.

Werking:
  1. bank_list_aspsps       - ontdek de exacte naam die Enable Banking voor
                               ING gebruikt (geen aannames, live opgezocht)
  2. bank_start_authorization - start de koppeling; geeft een URL terug die
                               JIJ zelf in je browser opent. Je logt daar
                               rechtstreeks bij ING in (nooit via ons of
                               Enable Banking) en geeft toestemming.
  3. Na het inloggen stuurt ING je terug naar onze eigen /bank/callback
     route (zie main.py) - die wisselt de eenmalige code om voor toegang
     en onthoudt welke rekeningen gekoppeld zijn.
  4. bank_list_accounts / bank_get_balance / bank_get_transactions - de
     eigenlijke opvraag-tools, werken met wat er bij stap 3 is vastgelegd.
"""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import jwt as pyjwt
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.config import (
    DATA_DIR,
    ENABLE_BANKING_APP_ID,
    ENABLE_BANKING_ENVIRONMENT,
    ENABLE_BANKING_PRIVATE_KEY_B64,
    ENABLE_BANKING_REDIRECT_URL,
)

bank_mcp = MCPServer("bank_mcp")

API_BASE = "https://api.enablebanking.com"
SESSION_FILE = DATA_DIR / "bank_session.json"
PENDING_STATE_FILE = DATA_DIR / "bank_pending_state.json"


def _error(e: Exception) -> str:
    return json.dumps({"error": f"{type(e).__name__}: {e}"})


def _get_private_key() -> bytes:
    if not ENABLE_BANKING_PRIVATE_KEY_B64:
        raise RuntimeError(
            "enable_banking_private_key is niet ingesteld in de add-on opties "
            "(base64-gecodeerde inhoud van je .pem-bestand)."
        )
    return base64.b64decode(ENABLE_BANKING_PRIVATE_KEY_B64)


def _build_jwt() -> str:
    if not ENABLE_BANKING_APP_ID:
        raise RuntimeError("enable_banking_app_id is niet ingesteld in de add-on opties.")
    private_key = _get_private_key()
    iat = int(datetime.now(timezone.utc).timestamp())
    body = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": iat,
        "exp": iat + 3600,
    }
    return pyjwt.encode(
        body, private_key, algorithm="RS256", headers={"kid": ENABLE_BANKING_APP_ID}
    )


def _headers() -> dict:
    return {"Authorization": f"Bearer {_build_jwt()}", "Content-Type": "application/json"}


def _load_session() -> Optional[dict]:
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return None


def _save_session(data: dict) -> None:
    SESSION_FILE.write_text(json.dumps(data, indent=2, default=str))


class AspspsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(default="NL", description="Twee-letterige landcode, bv. 'NL'")


@bank_mcp.tool(
    name="bank_list_aspsps",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def bank_list_aspsps(params: AspspsInput) -> str:
    """Haal de lijst met beschikbare banken (ASPSP's) op voor een land, met hun
    exacte naam zoals Enable Banking die verwacht. Gebruik dit om de precieze
    naam van ING te vinden voordat je bank_start_authorization aanroept -
    nooit raden naar de exacte schrijfwijze.

    Args:
        params: country, twee-letterige landcode (standaard 'NL')

    Returns:
        JSON-lijst met banknamen zoals Enable Banking ze kent.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/aspsps", params={"country": params.country}, headers=_headers()
            )
            resp.raise_for_status()
        return json.dumps(resp.json().get("aspsps", []), indent=2)
    except Exception as e:
        return _error(e)


class StartAuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aspsp_name: str = Field(..., description="Exacte banknaam, opgehaald via bank_list_aspsps")
    country: str = Field(default="NL", description="Twee-letterige landcode")
    valid_days: int = Field(default=90, ge=1, le=180, description="Hoe lang de toegang geldig blijft")


@bank_mcp.tool(
    name="bank_start_authorization",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
)
async def bank_start_authorization(params: StartAuthInput) -> str:
    """Start de koppeling met je bank. Geeft een URL terug die JIJ zelf moet
    openen in je browser - daar log je rechtstreeks bij je bank in (nooit via
    Claude of Enable Banking) en geef je toestemming voor welke rekeningen
    gedeeld worden. Na het inloggen stuurt je bank je automatisch terug, en
    wordt de koppeling vanzelf afgerond.

    Args:
        params: aspsp_name (exacte banknaam), country, valid_days (geldigheid)

    Returns:
        JSON met de URL om te openen.
    """
    try:
        state = str(uuid.uuid4())
        valid_until = (datetime.now(timezone.utc) + timedelta(days=params.valid_days)).isoformat()
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": params.aspsp_name, "country": params.country},
            "state": state,
            "redirect_url": ENABLE_BANKING_REDIRECT_URL,
            "psu_type": "personal",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{API_BASE}/auth", json=body, headers=_headers())
            resp.raise_for_status()
        data = resp.json()

        PENDING_STATE_FILE.write_text(json.dumps({"state": state}))

        return json.dumps(
            {
                "url": data.get("url"),
                "instructie": "Open deze URL zelf in je browser om bij je bank in te loggen.",
            },
            indent=2,
        )
    except Exception as e:
        return _error(e)


@bank_mcp.tool(
    name="bank_list_accounts",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def bank_list_accounts() -> str:
    """Lijst de op dit moment gekoppelde bankrekeningen op (na een geslaagde
    bank_start_authorization + inlogstap).

    Returns:
        JSON-lijst met gekoppelde rekeningen (uid, naam, IBAN indien bekend).
    """
    session = _load_session()
    if not session:
        return json.dumps(
            {"error": "Nog geen rekeningen gekoppeld. Gebruik eerst bank_start_authorization."}
        )
    return json.dumps(session.get("accounts", []), indent=2)


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_uid: str = Field(..., description="Rekening-uid, zie bank_list_accounts")


@bank_mcp.tool(
    name="bank_get_balance",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def bank_get_balance(params: AccountInput) -> str:
    """Haal het actuele saldo van een gekoppelde rekening op.

    Args:
        params: account_uid, zie bank_list_accounts

    Returns:
        JSON met saldogegevens.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/accounts/{params.account_uid}/balances", headers=_headers()
            )
            resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except Exception as e:
        return _error(e)


class TransactionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_uid: str = Field(..., description="Rekening-uid, zie bank_list_accounts")
    date_from: Optional[str] = Field(default=None, description="YYYY-MM-DD, optioneel")
    date_to: Optional[str] = Field(default=None, description="YYYY-MM-DD, optioneel")


@bank_mcp.tool(
    name="bank_get_transactions",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def bank_get_transactions(params: TransactionsInput) -> str:
    """Haal transacties van een gekoppelde rekening op, optioneel binnen een
    datumrange.

    Args:
        params: account_uid, en optioneel date_from/date_to (YYYY-MM-DD)

    Returns:
        JSON-lijst met transacties (bedrag, datum, omschrijving, tegenpartij).
    """
    try:
        query = {}
        if params.date_from:
            query["date_from"] = params.date_from
        if params.date_to:
            query["date_to"] = params.date_to
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/accounts/{params.account_uid}/transactions",
                params=query,
                headers=_headers(),
            )
            resp.raise_for_status()
        return json.dumps(resp.json().get("transactions", []), indent=2, default=str)
    except Exception as e:
        return _error(e)


async def handle_bank_callback(request: Request) -> HTMLResponse:
    """Publieke (niet-geauthenticeerde) route: ING/Enable Banking stuurt de
    gebruikers-browser hierheen terug na het inloggen bij de bank. Wisselt de
    eenmalige 'code' om voor echte toegang en onthoudt welke rekeningen
    gekoppeld zijn, zodat de MCP-tools ze daarna kunnen gebruiken.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    def page(title: str, body: str) -> HTMLResponse:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;max-width:480px;margin:60px auto;'>"
            f"<h2>{title}</h2><p>{body}</p></body></html>"
        )

    if error:
        return page("Koppeling mislukt", f"De bank meldde een fout: {error}. Sluit dit venster en probeer het opnieuw.")

    if not code:
        return page("Koppeling mislukt", "Geen code ontvangen van de bank. Sluit dit venster en probeer het opnieuw.")

    if PENDING_STATE_FILE.exists():
        pending = json.loads(PENDING_STATE_FILE.read_text())
        if pending.get("state") and pending.get("state") != state:
            return page(
                "Koppeling geweigerd",
                "De beveiligingscode klopt niet (mogelijk een verlopen of dubbele poging). "
                "Sluit dit venster en start de koppeling opnieuw.",
            )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_BASE}/sessions", json={"code": code}, headers=_headers()
            )
            resp.raise_for_status()
        session = resp.json()
        _save_session(session)
        if PENDING_STATE_FILE.exists():
            PENDING_STATE_FILE.unlink()
        aantal = len(session.get("accounts", []))
        return page(
            "Koppeling gelukt!",
            f"{aantal} rekening(en) succesvol gekoppeld. Je kunt dit venster sluiten en teruggaan naar Claude.",
        )
    except Exception as e:
        return page("Koppeling mislukt", f"Er ging iets mis bij het afronden: {e}")
