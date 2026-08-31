"""Configuratie voor de Claude Remote MCP Gateway.

Home Assistant Supervisor schrijft de add-on opties (ingesteld via de UI)
naar /data/options.json in de container. Voor lokaal draaien/testen buiten
Supervisor vallen we terug op omgevingsvariabelen.
"""

import json
import os
from pathlib import Path

OPTIONS_PATH = Path("/data/options.json")
DATA_DIR = Path("/data")


def _load_options() -> dict:
    if OPTIONS_PATH.exists():
        try:
            with open(OPTIONS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


_options = _load_options()


def _get(key: str, env_fallback: str, default: str | None = None) -> str | None:
    value = _options.get(key)
    if value not in (None, ""):
        return value
    env_value = os.environ.get(env_fallback)
    if env_value not in (None, ""):
        return env_value
    return default


GATEWAY_TOKEN: str | None = _get("gateway_token", "GATEWAY_TOKEN")

# Enable Banking (ING/PSD2) - private key komt base64-gecodeerd binnen omdat
# de Home Assistant add-on-configuratie geen multi-line velden ondersteunt.
ENABLE_BANKING_APP_ID: str | None = _get("enable_banking_app_id", "ENABLE_BANKING_APP_ID")
ENABLE_BANKING_PRIVATE_KEY_B64: str | None = _get(
    "enable_banking_private_key_b64", "ENABLE_BANKING_PRIVATE_KEY_B64"
)
ENABLE_BANKING_ENVIRONMENT: str = (
    _get("enable_banking_environment", "ENABLE_BANKING_ENVIRONMENT", "sandbox") or "sandbox"
)
ENABLE_BANKING_API_BASE = "https://api.enablebanking.com"
BANK_SESSION_FILE = str(DATA_DIR / "bank_session.json")
BANK_PENDING_STATE_FILE = str(DATA_DIR / "bank_pending_state.json")

# De publieke HTTPS-URL van deze gateway zelf (bv. https://mcp.jellevw.party),
# nodig als redirect_url waar Enable Banking de gebruiker na inloggen bij ING
# naar terugstuurt met een 'code'. Zonder https/publiek bereikbaar werkt de
# terugkeer-stap niet.
GATEWAY_PUBLIC_URL: str = (
    _get("gateway_public_url", "GATEWAY_PUBLIC_URL", "") or ""
).rstrip("/")
# Afgeleide, exacte redirect-URL die je 1-op-1 moet overnemen bij de
# 'Allowed Redirect URLs' registratie in het Enable Banking Control Panel.
ENABLE_BANKING_REDIRECT_URL: str = f"{GATEWAY_PUBLIC_URL}/bank/callback" if GATEWAY_PUBLIC_URL else ""
GARMIN_EMAIL: str | None = _get("garmin_email", "GARMIN_EMAIL")
GARMIN_PASSWORD: str | None = _get("garmin_password", "GARMIN_PASSWORD")
HA_AGENT_URL: str = _get("ha_agent_url", "HA_AGENT_URL", "http://homeassistant.local:8099") or (
    "http://homeassistant.local:8099"
)
HA_AGENT_KEY: str | None = _get("ha_agent_key", "HA_AGENT_KEY")
LOG_LEVEL: str = (_get("log_level", "LOG_LEVEL", "info") or "info").upper()
PORT: int = int(_get("port", "PORT", "8300") or "8300")

# Zorg dat de persistente datamap bestaat (voor Garmin sessie-tokens e.d.)
DATA_DIR.mkdir(parents=True, exist_ok=True)
GARMIN_TOKEN_DIR = str(DATA_DIR / ".garminconnect")
