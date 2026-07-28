"""Stage 4/5: merge scrape + enrichment, dedupe, score channel, export xlsx."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .common import DATA, norm_phone

COLUMNS = [
    "business_name", "channel", "opportunity", "gaps", "dm_draft",
    "status", "notes", "owner_name", "phone", "email",
    "instagram", "facebook", "website", "address", "city",
    "category", "rating", "reviews", "google_maps_url", "date_added",
]
# Stable cross-run identity. Not shown in the sheet; stored in the ledger.
KEY_FIELD = "key"


def to_row(place: dict, contact: dict, dm_channels: list[str]) -> dict:
    row = {
        "business_name": place.get("title", ""),
        "owner_name": contact.get("owner_name", ""),
        "phone": place.get("phone", "") or place.get("phoneUnformatted", ""),
        "email": contact.get("email", ""),
        "instagram": contact.get("instagram", ""),
        "facebook": contact.get("facebook", ""),
        "website": place.get("website", ""),
        "address": place.get("address", "")
        or place.get("street", ""),
        "city": place.get("city", ""),
        "category": place.get("categoryName", "")
        or (place.get("categories") or [""])[0],
        "rating": place.get("totalScore", ""),
        "reviews": place.get("reviewsCount", ""),
        "google_maps_url": place.get("url", ""),
        "date_added": date.today().isoformat(),
    }
    row["channel"] = score_lead(row, dm_channels)
    row["opportunity"], row["gaps"] = compute_gaps(row, place)
    row["dm_draft"] = draft_message(row)
    row["status"] = ""   # outreach tracking, filled in by hand
    row["notes"] = ""
    # Stable identity: Google place id first, then phone, then name+address.
    pid = str(place.get("place_id") or place.get("placeId")
              or place.get("cid") or "").strip()
    row[KEY_FIELD] = (
        pid
        or norm_phone(row["phone"])
        or f"{row['business_name'].lower().strip()}|"
           f"{row['address'].lower().strip()}"
    )
    return row


def compute_gaps(row: dict, place: dict | None = None) -> tuple[int, str]:
    """Score how much marketing help a business likely needs (0-10).

    High score = strong prospect for local-marketing services. Signals that
    only exist in the raw scrape (claimed profile, ad pixels) are skipped
    when unavailable, so this also works when re-scoring ledger rows.
    """
    place = place or {}
    gaps, score = [], 0
    if not row.get("website"):
        gaps.append("no website")
        score += 3
    if place.get("claimed") is False:
        gaps.append("unclaimed GBP")
        score += 3
    if not row.get("instagram"):
        gaps.append("no Instagram")
        score += 2
    if row.get("website") and (place.get("has_fb_pixel") is False
                               and place.get("has_google_tag") is False):
        gaps.append("no ad tracking")
        score += 1
    try:
        revs = int(row.get("reviews") or 0)
    except (TypeError, ValueError):
        revs = 0
    if revs < 50:
        gaps.append("few reviews")
        score += 1
    return score, "; ".join(gaps)


def _plural(category: str) -> str:
    c = (category or "business").lower()
    if c.endswith(("s", "x", "z", "ch", "sh")):
        return c + "es"
    return c + "s"


def draft_message(row: dict) -> str:
    """A short, editable DM opener personalized from name, category, rating."""
    owner = (row.get("owner_name") or "").split(" (")[0].strip()
    first = owner.split()[0] if owner else ""
    greet = f"Hi {first}" if first else "Hi there"
    biz = (row.get("business_name") or "").strip()
    city = (row.get("city") or "").strip()
    cat_plural = _plural(row.get("category") or "local business")
    try:
        rating = float(row.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        revs = int(row.get("reviews") or 0)
    except (TypeError, ValueError):
        revs = 0

    loc = f" in {city}" if city else ""
    gaps = row.get("gaps") or ""

    # Pitch the gap, not a generic line. Priority: website > GBP > social.
    if "no website" in gaps:
        hook = (f"I came across {biz}{loc} — great reviews, but I noticed "
                f"people can't book or browse you online yet.")
        pitch = (f"I build simple sites for {cat_plural} that turn Google "
                 f"searches into booked appointments — mind if I share a "
                 f"quick idea here?")
    elif "unclaimed GBP" in gaps:
        hook = (f"I found {biz}{loc} on Google and noticed the profile "
                f"looks unclaimed — you're likely losing calls to "
                f"competitors who show up polished.")
        pitch = ("I help local businesses take over and optimize their "
                 "Google listing — takes a week, mind if I share how?")
    elif rating >= 4.5 and revs >= 10:
        hook = (f"{biz} stood out — {rating:g}★ across {revs} reviews "
                f"is no accident.")
        pitch = (f"I help {cat_plural} turn that reputation into more "
                 f"booked appointments without leaning harder on ads — "
                 f"mind if I share a quick idea here?")
    else:
        hook = (f"I came across {biz}{loc} and loved what you're doing."
                if biz else
                "I came across your page and loved what you're doing.")
        pitch = (f"I help {cat_plural} get found by more local customers "
                 f"on Google — mind if I share a quick idea here?")

    return f"{greet}! {hook} {pitch}"


def score_lead(row: dict, dm_channels: list[str]) -> str:
    """DM-first routing: any social -> DM queue, else email, else needs-research."""
    has_social = any(row.get(ch) for ch in dm_channels)
    if has_social:
        return "DM"
    if row.get("email"):
        return "Email"
    return "Needs research"


def _sort_key(row: dict):
    """Sellability first: opportunity (gaps) desc, then social proof desc.

    A business with fixable gaps is a better prospect than one that's
    already winning; among equals, the more-established one goes first.
    """
    try:
        opp = int(row.get("opportunity") or 0)
    except (TypeError, ValueError):
        opp = 0
    try:
        rating = float(row.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        revs = int(row.get("reviews") or 0)
    except (TypeError, ValueError):
        revs = 0
    return (-opp, -(rating * min(revs, 500)))


def build_rows(places: list[dict], contacts: list[dict], cfg: dict) -> list[dict]:
    """Make scored rows for one scrape batch, deduped within the batch by key."""
    dm_channels = cfg["dm_channels"]
    rows = [to_row(p, c, dm_channels) for p, c in zip(places, contacts)]
    seen, out = set(), []
    for r in rows:
        k = r.get(KEY_FIELD)
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        out.append(r)
    return out


def _write_tab(wb: Workbook, title: str, rows: list[dict]):
    ws = wb.create_sheet(title)
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(color="FFFFFF", bold=True)
    for c, col in enumerate(COLUMNS, 1):
        cell = ws.cell(1, c, col.replace("_", " ").title())
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left")
    for r, row in enumerate(rows, 2):
        for c, col in enumerate(COLUMNS, 1):
            cell = ws.cell(r, c, row.get(col, ""))
            if col == "dm_draft":
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    widths = {"business_name": 28, "gaps": 30, "dm_draft": 60, "status": 12,
              "notes": 24, "email": 26, "website": 30,
              "instagram": 26, "facebook": 26, "address": 32,
              "google_maps_url": 22, "opportunity": 11}
    for c, col in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(col, 14)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}1"


def write_workbook(rows: list[dict], cfg: dict, path=None,
                   new_keys: set | None = None) -> str:
    """Write the deliverable xlsx (DM First / Email Second / All) from rows.

    If new_keys is given, adds a "New This Run" tab with just those leads.
    """
    rows = sorted(rows, key=_sort_key)
    dm = [r for r in rows if r.get("channel") == "DM"]
    email = [r for r in rows if r.get("channel") == "Email"]

    wb = Workbook()
    wb.remove(wb.active)  # drop the default empty sheet
    _write_tab(wb, "DM First", dm)
    _write_tab(wb, "Email Second", email)
    if new_keys is not None:
        fresh = [r for r in rows if r.get(KEY_FIELD) in new_keys]
        _write_tab(wb, "New This Run", fresh)
    _write_tab(wb, "All", rows)

    out = Path(path) if path else (DATA / cfg["output"]["xlsx_name"])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"[sheet] {len(rows)} leads -> {out}")
    print(f"[sheet]   DM First: {len(dm)} | Email Second: {len(email)} | "
          f"Needs research: {len(rows) - len(dm) - len(email)}")
    return str(out)
