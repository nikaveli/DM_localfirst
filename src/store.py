"""Per-city master ledger for cross-run dedup.

One CSV per city/state under leads_db/ (committed to the repo). It is both the
dedup source of truth and the cumulative dataset: each run appends only
businesses whose key isn't already present, so re-running the same city never
duplicates a lead.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .build_sheet import COLUMNS, KEY_FIELD
from .common import ROOT

LEADS_DB = ROOT / "leads_db"
FIELDS = COLUMNS + [KEY_FIELD]


def slugify(city: str, state: str | None) -> str:
    raw = f"{city}-{state}" if state else (city or "")
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug or "leads"


def master_path(slug: str) -> Path:
    return LEADS_DB / f"{slug}.csv"


def load_master(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def merge(master: list[dict], new_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (all_rows, added_rows). Existing keys win; new keys are appended."""
    existing = {r.get(KEY_FIELD) for r in master if r.get(KEY_FIELD)}
    added = []
    for r in new_rows:
        k = r.get(KEY_FIELD)
        if k and k in existing:
            continue
        if k:
            existing.add(k)
        added.append(r)
    return master + added, added


def save_master(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in FIELDS})
