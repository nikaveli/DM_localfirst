"""Orchestrator. Scrape -> enrich -> build spreadsheet.

  python -m src.run --city "Austin" --state "Texas" --niche "med spa" --max 100
  python -m src.run --city "Austin" --niche "med spa" --skip-scrape
"""
from __future__ import annotations

import argparse
import json
import os

from . import build_sheet, enrich, scrape_gbp, scrape_outscraper, store
from .common import DATA, RAW_PATH, load_config, to_state_code


def filter_state(places, contacts, requested_state):
    """Drop out-of-state spillover. No-op if the state can't be resolved."""
    want = to_state_code(requested_state)
    if not want:
        return places, contacts
    keep_p, keep_c, dropped = [], [], 0
    for p, c in zip(places, contacts):
        pc = to_state_code(p.get("state") or p.get("state_code"))
        if pc and pc != want:
            dropped += 1
            continue
        keep_p.append(p)
        keep_c.append(c)
    if dropped:
        print(f"[filter] dropped {dropped} out-of-state (kept {len(keep_p)})")
    return keep_p, keep_c


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
    # Each --category may itself be comma-separated ("med spa, day spa").
    raw_niches = args.niche or ["med spa", "day spa", "wellness center"]
    niches = [n.strip() for grp in raw_niches for n in grp.split(",")
              if n.strip()]
    print(f"[run] provider={provider} city={args.city!r} niches={niches}")

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

    # Drop out-of-state spillover (small cities pull in nearby results).
    places, contacts = filter_state(places, contacts, args.state)

    # Cross-run dedup: merge this batch into the per-city master ledger.
    batch = build_sheet.build_rows(places, contacts, cfg)
    slug = store.slugify(args.city, args.state)
    path = store.master_path(slug)
    master = store.load_master(path)
    elsewhere = store.keys_in_other_ledgers(path)
    own_keys = {r.get(build_sheet.KEY_FIELD) for r in master}
    skipped = sum(1 for r in batch
                  if r.get(build_sheet.KEY_FIELD) in elsewhere
                  and r.get(build_sheet.KEY_FIELD) not in own_keys)
    all_rows, added = store.merge(master, batch, exclude=elsewhere)
    if skipped:
        print(f"[dedup] skipped {skipped} already owned by another city ledger")
    # Backfill ledger rows that predate newer columns (tier, status, drafts).
    for r in all_rows:
        if not r.get("business_name"):
            continue
        if not r.get("website_status"):
            r["website_status"] = build_sheet.website_status(r.get("website"))
        if not r.get("tier"):
            r["tier"] = build_sheet.pitch_tier(
                r["website_status"], build_sheet.as_int(r.get("reviews")))
        if not r.get("gaps") and not r.get("opportunity"):
            r["opportunity"], r["gaps"] = build_sheet.compute_gaps(r)
            r["dm_draft"] = build_sheet.draft_message(r)
        elif not r.get("dm_draft"):
            r["dm_draft"] = build_sheet.draft_message(r)
    store.save_master(path, all_rows)
    print(f"[run] ledger {slug}: +{len(added)} new "
          f"(scraped {len(batch)}, master now {len(all_rows)})")

    new_keys = {r.get(build_sheet.KEY_FIELD) for r in added}
    out = build_sheet.write_workbook(
        all_rows, cfg, DATA / cfg["output"]["xlsx_name"], new_keys=new_keys)
    print(f"[run] done -> {out}")
    write_step_summary(args, niches, all_rows, added)


def write_step_summary(args, niches, all_rows, added):
    """Post results to the GitHub Actions run page (no download needed)."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    dm = sum(1 for r in all_rows if r.get("channel") == "DM")
    em = sum(1 for r in all_rows if r.get("channel") == "Email")
    top = sorted(added or all_rows, key=build_sheet._sort_key)[:5]
    lines = [
        f"## Leads: {', '.join(niches)} — {args.city}, {args.state or ''}",
        "",
        f"| New this run | Total in ledger | DM First | Email Second |",
        f"|---|---|---|---|",
        f"| **{len(added)}** | {len(all_rows)} | {dm} | {em} |",
        "",
        f"### Top {'new ' if added else ''}prospects (by opportunity)",
        "| Business | Opp | Gaps | Rating |",
        "|---|---|---|---|",
    ]
    for r in top:
        lines.append(
            f"| {r.get('business_name','')} | {r.get('opportunity','')} "
            f"| {r.get('gaps','')} | {r.get('rating','')}★ "
            f"({r.get('reviews','')}) |")
    lines.append("\nSpreadsheet: download the `leads-run-*` artifact below.")
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
