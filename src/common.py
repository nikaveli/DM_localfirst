"""Shared helpers: config loading, paths, light normalization."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_PATH = DATA / "raw_places.json"

load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def apify_token() -> str:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise SystemExit(
            "APIFY_TOKEN missing. Copy .env.example to .env and add your token."
        )
    return token


def outscraper_key() -> str:
    token = os.getenv("OUTSCRAPER_API_KEY")
    if not token:
        raise SystemExit(
            "OUTSCRAPER_API_KEY missing. Copy .env.example to .env and add it."
        )
    return token


_PHONE_RE = re.compile(r"\D+")


def norm_phone(phone: str | None) -> str:
    """Digits only, so dedupe survives formatting differences."""
    if not phone:
        return ""
    return _PHONE_RE.sub("", phone)


def norm_url(url: str | None) -> str:
    if not url:
        return ""
    return url.strip().lower().rstrip("/")


_NAME2CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_CODES = set(_NAME2CODE.values())
# common shorthand the user might type
_ALIASES = {"colo": "CO", "calif": "CA", "cali": "CA", "mass": "MA",
            "penn": "PA", "wash": "WA", "tex": "TX", "fla": "FL"}


def lookup_zips(city: str, state: str | None, timeout: int = 15) -> list[str]:
    """All USPS zip codes for a city, via the free Zippopotam API (no key).

    Used for proximity search: one query per zip surfaces businesses that a
    single city-wide search never ranks. Returns [] if lookup fails, so the
    caller can fall back to a plain city search.
    """
    import requests

    code = to_state_code(state)
    if not city or not code:
        return []
    url = f"http://api.zippopotam.us/us/{code.lower()}/{city.strip().lower()}"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return []
        places = r.json().get("places", [])
        return sorted({p["post code"] for p in places if p.get("post code")})
    except Exception:
        return []


def to_state_code(s: str | None) -> str:
    """Normalize 'Colorado' / 'CO' / 'colo' -> 'CO'. '' if unresolvable."""
    if not s:
        return ""
    s = s.strip()
    if len(s) == 2 and s.upper() in _CODES:
        return s.upper()
    low = s.lower()
    return _NAME2CODE.get(low) or _ALIASES.get(low, "")
