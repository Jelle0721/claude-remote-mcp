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
