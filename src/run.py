"""Orchestrator. Scrape -> enrich -> build spreadsheet.

  python -m src.run --city "Austin" --state "Texas" --niche "med spa" --max 100
  python -m src.run --city "Austin" --niche "med spa" --skip-scrape
"""
from __future__ import annotations

import argparse
import json

from . import build_sheet, enrich, scrape_gbp, scrape_outscraper, store
from .common import DATA, RAW_PATH, load_config


def parse_args():
    p = argparse.ArgumentParser(description="DM-first local lead engine")
    p.add_argument("--city", required=True, help="City, e.g. 'Austin'")
    p.add_argument("--state", default=None, help="State, e.g. 'Texas' (US)")
    p.add_argument("--category", "--niche", action="append", default=[],
                   dest="niche",
                   help="Business category / search term; repeatable")
    p.add_argument("--max", type=int, default=None,
                   help="Max places per category (overrides config)")
    p.add_argument("--provider", choices=["outscraper", "apify"], default=None,
                   help="Scrape backend (overrides config)")
    p.add_argument("--skip-scrape", action="store_true",
                   help="Reuse data/raw_places.json, just enrich + build "
                        "(Apify provider only)")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    provider = args.provider or cfg["scrape"]["provider"]
    niches = args.niche or ["med spa", "day spa", "wellness center"]
    print(f"[run] provider={provider} city={args.city!r}")

    if args.skip_scrape:
        if not RAW_PATH.exists():
            raise SystemExit(f"No cached scrape at {RAW_PATH}; run without "
                             "--skip-scrape first.")
        with open(RAW_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        print(f"[run] reusing {len(raw)} cached places")
        if provider == "outscraper":
            pairs = [scrape_outscraper._to_internal(p) for p in raw]
            places = [p for p, _ in pairs]
            contacts = [c for _, c in pairs]
        else:
            places = raw
            contacts = enrich.enrich_all(places, cfg)
    elif provider == "outscraper":
        # Outscraper scrapes + enriches in one call.
        places, contacts = scrape_outscraper.run(
            niches, args.city, args.state, cfg, args.max)
    else:
        places = scrape_gbp.run(niches, args.city, args.state, cfg, args.max)
        contacts = enrich.enrich_all(places, cfg)

    if not places:
        raise SystemExit("No places returned. Check city/niche or the run logs.")

    # Cross-run dedup: merge this batch into the per-city master ledger.
    batch = build_sheet.build_rows(places, contacts, cfg)
    slug = store.slugify(args.city, args.state)
    path = store.master_path(slug)
    master = store.load_master(path)
    all_rows, added = store.merge(master, batch)
    store.save_master(path, all_rows)
    print(f"[run] ledger {slug}: +{len(added)} new "
          f"(scraped {len(batch)}, master now {len(all_rows)})")

    out = build_sheet.write_workbook(all_rows, cfg, DATA / cfg["output"]["xlsx_name"])
    print(f"[run] done -> {out}")


if __name__ == "__main__":
    main()
