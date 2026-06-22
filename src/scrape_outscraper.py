"""Stage 1+2 (Outscraper backend): scrape GBP AND enrich in one call.

Outscraper's Google Maps Search with the `domains_service` enrichment returns
email, owner name/title, and social links alongside the place data, so there's
no separate Python enrichment pass. Output is normalized to the same internal
schema build_sheet expects (Apify-style keys), so the spreadsheet stage is
provider-agnostic.
"""
from __future__ import annotations

import json

from urllib.parse import urlparse

from outscraper import ApiClient

from .common import RAW_PATH, load_config, outscraper_key

# Generic platform paths that are NOT real profiles — Outscraper sometimes
# returns these (e.g. instagram.com/reel). Drop them.
IG_JUNK = {"reel", "reels", "p", "explore", "accounts", "stories", "tv", "about"}
FB_JUNK = {"sharer", "dialog", "plugins", "tr", "groups", "watch", "events",
           "pages", "people", "profile.php", "reel", "story.php"}


def _norm_social(val, base: str, junk: set) -> str:
    """Normalize to a profile URL; return '' for junk/generic paths.

    Outscraper may return a full URL or a bare handle. We keep only values
    whose first path segment looks like a real profile/page handle.
    """
    if not val:
        return ""
    val = str(val).strip().rstrip("/")
    if val.lower().startswith("http"):
        seg = (urlparse(val).path.strip("/").split("/") or [""])[0]
        full = val
    else:
        seg = val.lstrip("@/").split("/")[0]
        full = base + seg
    if not seg or seg.lower() in junk:
        return ""
    return full


def _iter_places(res):
    """Yield place dicts whether res is list-of-lists or a flat list of dicts."""
    for group in res or []:
        if isinstance(group, dict):
            yield group
        elif isinstance(group, list):
            for p in group:
                if isinstance(p, dict):
                    yield p


def _to_internal(p: dict):
    """Map one Outscraper place -> (place, contact) in our internal schema."""
    place = {
        "place_id": p.get("place_id") or p.get("google_id") or p.get("cid"),
        "title": p.get("name", ""),
        "phone": p.get("phone", "") or p.get("phone_1", ""),
        "website": p.get("website", "") or p.get("site", ""),
        "address": p.get("full_address", "") or p.get("address", ""),
        "city": p.get("city", ""),
        "categoryName": p.get("type", "") or p.get("category", ""),
        "totalScore": p.get("rating", ""),
        "reviewsCount": p.get("reviews", ""),
        "url": p.get("location_link", ""),
    }
    owner = (p.get("email_1_full_name") or "").strip()
    title = (p.get("email_1_title") or "").strip()
    owner_name = f"{owner} ({title})" if owner and title else owner
    contact = {
        "email": p.get("email_1", "") or p.get("email_2", ""),
        "facebook": _norm_social(p.get("facebook", ""),
                                 "https://facebook.com/", FB_JUNK),
        "instagram": _norm_social(p.get("instagram", ""),
                                  "https://instagram.com/", IG_JUNK),
        "owner_name": owner_name,
    }
    return place, contact


def run(niches, city, state, cfg, max_places=None):
    """Return (places, contacts) already normalized + enriched."""
    client = ApiClient(outscraper_key())
    s = cfg["scrape"]
    limit = max_places or s["max_places"]
    loc = ", ".join(x for x in [city, state, "USA"] if x)
    queries = [f"{n}, {loc}" for n in niches]
    enrichment = ["domains_service"] if s.get("outscraper_enrichment", True) else None

    print(f"[scrape] outscraper queries={queries} limit={limit}/query "
          f"enrichment={enrichment}")
    res = client.google_maps_search(
        queries,
        limit=limit,
        language=s["language"],
        region=s["country_code"].upper(),
        enrichment=enrichment,
        drop_duplicates=True,
    )

    # Response shape varies: sometimes list-of-lists (one list per query),
    # sometimes a flat list of place dicts. Handle both.
    raw, places, contacts = [], [], []
    for p in _iter_places(res):
        raw.append(p)
        place, contact = _to_internal(p)
        places.append(place)
        contacts.append(contact)

    print(f"[scrape] {len(places)} places returned")
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PATH, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
    return places, contacts


if __name__ == "__main__":
    run(["med spa"], "Austin", "Texas", load_config(), max_places=3)
