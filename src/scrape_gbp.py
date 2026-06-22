"""Stage 1: scrape Google Business Profiles via the Apify Google Maps actor."""
from __future__ import annotations

import json
from typing import Iterable

from apify_client import ApifyClient

from .common import RAW_PATH, apify_token, load_config


def build_input(
    niches: Iterable[str],
    city: str,
    state: str | None,
    cfg: dict,
    max_places: int | None,
) -> dict:
    s = cfg["scrape"]
    e = cfg["enrichment"]
    payload: dict = {
        "searchStringsArray": list(niches),
        "city": city,
        "countryCode": s["country_code"],
        "language": s["language"],
        "maxCrawledPlacesPerSearch": max_places or s["max_places"],
        "skipClosedPlaces": s["skip_closed"],
        "website": s["website_filter"],
    }
    if state:
        payload["state"] = state
    if s.get("min_stars"):
        payload["placeMinimumStars"] = s["min_stars"]
    # Optional: let Apify do the email/social crawl instead of our Python pass.
    if e.get("use_apify_contacts"):
        payload["scrapeContacts"] = True
    return payload


def run(niches, city, state, cfg, max_places=None) -> list[dict]:
    client = ApifyClient(apify_token())
    actor = cfg["scrape"]["actor"]
    run_input = build_input(niches, city, state, cfg, max_places)

    print(f"[scrape] actor={actor} city={city!r} niches={list(niches)} "
          f"max={run_input['maxCrawledPlacesPerSearch']}/term")
    run_info = client.actor(actor).call(run_input=run_input)
    dataset_id = run_info["defaultDatasetId"]

    items = list(client.dataset(dataset_id).iterate_items())
    print(f"[scrape] {len(items)} places returned "
          f"(run https://console.apify.com/actors/runs/{run_info['id']})")

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PATH, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2, ensure_ascii=False)
    return items


if __name__ == "__main__":
    cfg = load_config()
    run(["med spa"], "Austin", "Texas", cfg, max_places=10)
