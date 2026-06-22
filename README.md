# DM_localfirst

Local-business lead engine for **DM-first outreach**. Scrapes Google Business
Profiles (GBP) by city + niche via Apify, enriches each lead with email +
Facebook + Instagram (and best-effort owner name), scores them by how
reachable they are, and exports a single spreadsheet split into two queues:

1. **DM First** — businesses with an Instagram or Facebook presence.
2. **Email Second** — businesses with no social, fall back to email.

## Pipeline

Two interchangeable scrape backends (set `scrape.provider` in `config.yaml` or
`--provider`):

- **outscraper** (default) — scrapes GBP **and** enriches (email, socials,
  owner name + title) in a single API call. Recommended.
- **apify** — `compass/crawler-google-places` for the scrape, then a free
  Python pass crawls each website for email/socials/owner.

```
1. SCRAPE   GBP by city + niche  ->  name, address, phone, website, rating, category
2. ENRICH   email, FB, IG, owner ->  built-in (outscraper) OR free crawl (apify)
3. SCORE    rank by DM-ability    ->  has IG/FB? -> DM queue. else -> Email queue.
4. OUTPUT   leads.xlsx            ->  tabs: "DM First" / "Email Second" / "All"
```

### What comes from where

| Field        | Source                              | Fill rate    |
|--------------|-------------------------------------|--------------|
| Name         | GBP (Apify)                         | ~100%        |
| Address      | GBP (Apify)                         | ~100%        |
| Phone        | GBP (Apify)                         | ~90%         |
| Website      | GBP (Apify)                         | ~60-80%      |
| Category     | GBP (Apify)                         | ~100%        |
| Rating/#revs | GBP (Apify)                         | ~90%         |
| Email        | enrichment (outscraper / crawl)     | ~40-60%      |
| Facebook     | enrichment (outscraper / crawl)     | ~40-60%      |
| Instagram    | enrichment (outscraper / crawl)     | ~30-50%      |
| Owner name   | outscraper field / heuristic crawl  | ~30-50% / ~20-40% |

> Email, socials, and owner name are **not** in GBP. With outscraper they come
> back as structured fields (`email_1_full_name`/`email_1_title` give the owner);
> with apify they're inferred by crawling each website. Coverage depends on how
> many businesses have a working site. Note: enrichment **socials** can be noisy
> (occasionally mismatched) — sanity-check before DMing; emails are reliable.

## Setup

```bash
cd ~/DM_localfirst
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then paste your OUTSCRAPER_API_KEY into .env
```

Get your key at https://app.outscraper.com/profile (Outscraper, default) or
https://console.apify.com/account/integrations (Apify, if you switch providers).

## Run

```bash
# One city + niche, 100 places, full pipeline -> data/leads.xlsx
python -m src.run --city "Austin" --state "Texas" --niche "med spa" --max 100

# Multiple niches in one city
python -m src.run --city "Austin" --state "Texas" \
    --niche "med spa" --niche "day spa" --niche "wellness center" --max 75

# Force a provider for one run
python -m src.run --city "Austin" --niche "med spa" --provider apify

# Re-build the sheet from the last raw pull (no new API spend)
python -m src.run --city "Austin" --niche "med spa" --skip-scrape
```

Output lands in `data/`:
- `raw_places.json` — exactly what Apify returned (audit trail)
- `leads.xlsx` — the deliverable, three tabs

## Run on GitHub (no laptop needed)

One-time setup:

1. Add your key as a repo secret:
   `Settings -> Secrets and variables -> Actions -> New repository secret`
   name `OUTSCRAPER_API_KEY`, value = your key.
   (Or via CLI: `gh secret set OUTSCRAPER_API_KEY --repo nikaveli/DM_localfirst`.)

Each run:

2. `Actions` tab -> **Scrape leads** -> **Run workflow**.
3. Enter **category**, **city**, **state** (+ optional max) and click Run.
4. Download the spreadsheet from the run's **Artifacts** (`leads-run-<n>`).

### Cross-run dedup

Each city/state keeps a master ledger at `leads_db/<city-state>.csv`, committed
back to the repo after every run. The dedup key is Google's stable `place_id`
(falling back to phone, then name+address). Re-running the **same city** only
appends businesses not already in that ledger — no duplicate leads — and the
spreadsheet is rebuilt from the full deduped ledger each time. The
`date_added` column shows when each lead first appeared, so you can spot what's
new in a given run.

### DM drafts & out-of-state filter

- **`dm_draft` column** — every lead gets a short, editable DM opener
  personalized from owner first name (when known), business name, category, and
  rating/review count. The "DM First" tab is copy-paste ready; tweak the
  template in `src/build_sheet.py::draft_message`.
- **State filter** — small cities sometimes return nearby out-of-state results.
  When you pass a state, anything whose Google address resolves to a different
  state is dropped before it enters the ledger. Accepts `Colorado`, `CO`, or
  common shorthand like `colo`.

## Cost

- **Outscraper** (default): Google Maps ~**$3 / 1,000 places**, plus the
  `domains_service` email/contact enrichment (per Outscraper pricing). One call,
  owner + email + socials included.
- **Apify**: base scrape **$0.004 / place** (~$0.40 / 100), free Python
  enrichment **$0**, or Apify contact enrichment **+$0.002 / place**.

## Outreach workflow (DM first, email second)

The "DM First" tab is your daily action list. Work it top-down (sorted by
rating x review count = social proof / likely active business). Log replies,
then anything that doesn't convert + everyone in "Email Second" gets the email
sequence. Keep the channel-priority logic in `src/build_sheet.py::score_lead`.

## Config

`config.yaml` holds defaults (language, country, min stars, dedupe rules,
enrichment toggles). CLI flags override config.

## Compliance note

GBP data is public business info. Owner names can be personal data — only
collect/use what you have a legitimate basis for, honor opt-outs, and follow
CAN-SPAM (email) and the platforms' DM/automation rules. This repo collects
business contact points; it does **not** automate sending.
