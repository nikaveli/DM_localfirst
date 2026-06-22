"""Stage 2/3: free enrichment. Crawl each business website for email +
Facebook + Instagram, and take a best-effort guess at the owner name.

Only runs when Apify contact enrichment is OFF. If the raw place already has
emails/socials (Apify did it), we just read them through.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
FB_RE = re.compile(r"https?://(?:www\.)?facebook\.com/[^\"'\s>?#]+", re.I)
IG_RE = re.compile(r"https?://(?:www\.)?instagram\.com/[^\"'\s>?#]+", re.I)
# crude owner-name capture near owner/founder words. Keyword match is
# case-insensitive; the captured name stays case-sensitive (must be Capitalized).
OWNER_RE = re.compile(
    r"(?i:owner|founder|owned by|proprietor|principal)[:\s\-]{1,4}"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
)

JUNK_EMAIL = ("example.com", "sentry", "wixpress", "@2x", ".png", ".jpg", ".gif")
JUNK_FB = ("/sharer", "/dialog", "/plugins", "/tr?", "facebook.com/groups")
JUNK_IG = ("/p/", "/explore", "/accounts")


def _clean_first(matches, junk) -> str:
    for m in matches:
        low = m.lower()
        if not any(j in low for j in junk):
            return m.rstrip("/.,)")
    return ""


def _fetch(url: str, timeout: int, ua: str) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": ua},
                         allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get(
                "content-type", ""):
            return r.text
    except requests.RequestException:
        pass
    return ""


def enrich_one(website: str, cfg: dict) -> dict:
    """Return {email, facebook, instagram, owner_name} from a website."""
    out = {"email": "", "facebook": "", "instagram": "", "owner_name": ""}
    if not website:
        return out

    e = cfg["enrichment"]
    if not urlparse(website).scheme:
        website = "https://" + website
    base = website

    html_blob = ""
    for page in e["crawl_pages"]:
        url = urljoin(base + "/", page) if page else base
        html = _fetch(url, e["request_timeout"], e["user_agent"])
        if not html:
            continue
        html_blob += "\n" + html
        # stop early once we have the high-value fields
        if (EMAIL_RE.search(html_blob) and FB_RE.search(html_blob)
                and IG_RE.search(html_blob)):
            break

    if not html_blob:
        return out

    text = BeautifulSoup(html_blob, "html.parser").get_text(" ")

    emails = [m for m in EMAIL_RE.findall(html_blob)
              if not any(j in m.lower() for j in JUNK_EMAIL)]
    out["email"] = emails[0] if emails else ""
    out["facebook"] = _clean_first(FB_RE.findall(html_blob), JUNK_FB)
    out["instagram"] = _clean_first(IG_RE.findall(html_blob), JUNK_IG)
    m = OWNER_RE.search(text)
    out["owner_name"] = m.group(1).strip() if m else ""
    return out


def _from_apify(place: dict) -> dict:
    """If Apify already enriched contacts, read them instead of crawling."""
    emails = place.get("emails") or []
    socials = " ".join(str(s) for s in (place.get("socialMedia") or {}).values()) \
        if isinstance(place.get("socialMedia"), dict) else ""
    fb = _clean_first(FB_RE.findall(socials), JUNK_FB)
    ig = _clean_first(IG_RE.findall(socials), JUNK_IG)
    return {
        "email": emails[0] if emails else "",
        "facebook": fb,
        "instagram": ig,
        "owner_name": "",
    }


def enrich_all(places: list[dict], cfg: dict) -> list[dict]:
    use_apify = cfg["enrichment"].get("use_apify_contacts")
    results = [None] * len(places)

    if use_apify:
        for i, p in enumerate(places):
            results[i] = _from_apify(p)
        print(f"[enrich] read Apify contacts for {len(places)} places")
        return results

    workers = cfg["enrichment"]["max_workers"]
    print(f"[enrich] crawling {len(places)} websites (free), "
          f"{workers} workers...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(enrich_one, p.get("website", ""), cfg): i
            for i, p in enumerate(places)
        }
        done = 0
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception:
                results[i] = {"email": "", "facebook": "",
                              "instagram": "", "owner_name": ""}
            done += 1
            if done % 25 == 0:
                print(f"[enrich]   {done}/{len(places)}")
    hits = sum(1 for r in results if r and (r["email"] or r["facebook"]
                                            or r["instagram"]))
    print(f"[enrich] done. {hits}/{len(places)} got at least one contact.")
    return results
