# DM_localfirst

Local-business lead engine for **DM-first outreach**. Scrapes Google Business
Profiles (GBP) by city + niche via Apify, enriches each lead with email +
Facebook + Instagram (and best-effort owner name), scores them by how
reachable they are, and exports a single spreadsheet split into two queues:

1. **DM First** — businesses with an Instagram or Facebook presence.
2. **Email Second** — businesses with no social, fall back to email.

## Pipeline

```
1. SCRAPE   Apify Google Places  ->  name, address, phone, website, rating, category
2. ENRICH   crawl each website   ->  email, Facebook URL, Instagram URL
3. ENRICH   site/social (free)   ->  owner name (best-effort, lower fill rate)
4. SCORE    rank by DM-ability    ->  has IG/FB? -> DM queue. else -> Email queue.
5. OUTPUT   leads.xlsx            ->  tabs: "DM First" / "Email Second" / "All"
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
| Email        | website crawl (free enrich)         | ~40-60%      |
| Facebook     | website crawl (free enrich)         | ~40-60%      |
| Instagram    | website crawl (free enrich)         | ~30-50%      |
| Owner name   | site/FB about, heuristic (free)     | ~20-40%      |

> Email, socials, and owner name are **not** in GBP. They are inferred in a
> second pass. Coverage depends on how many businesses have a working website.

## Setup

```bash
cd ~/DM_localfirst
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then paste your APIFY_TOKEN into .env
```

Get your token at https://console.apify.com/account/integrations

## Run

```bash
# One city + niche, 100 places, full pipeline -> data/leads.xlsx
python -m src.run --city "Austin" --state "Texas" --niche "med spa" --max 100

# Multiple niches in one city
python -m src.run --city "Austin" --state "Texas" \
    --niche "med spa" --niche "day spa" --niche "wellness center" --max 75

# Skip the (paid) scrape and re-run enrichment + sheet on the last raw pull
python -m src.run --city "Austin" --niche "med spa" --skip-scrape
```

Output lands in `data/`:
- `raw_places.json` — exactly what Apify returned (audit trail)
- `leads.xlsx` — the deliverable, three tabs

## Cost (Apify, free tier rate)

- Base scrape: **$0.004 / place** (~$0.40 per 100 leads).
- Free Python enrichment: **$0** (just your bandwidth/time).
- Optional `enrichment.use_apify_contacts: true` in `config.yaml` swaps the
  Python crawl for Apify's contact enrichment at **+$0.002 / place** — higher
  fill rate, no local crawling.

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
