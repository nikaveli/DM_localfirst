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
