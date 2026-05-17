"""
Hantavirus Dashboard Auto-Updater
Scrapes WHO, CDC, and BBC News for the latest case data.
No API key required — completely free to run.
"""

import re
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── URLs to scrape ────────────────────────────────────────────────────────────
SOURCES = {
    "WHO": [
        "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON599",
        "https://www.who.int/news/item/07-05-2026-hantavirus",
        "https://www.who.int/emergencies/disease-outbreak-news",
    ],
    "CDC": [
        "https://www.cdc.gov/hantavirus/index.html",
        "https://www.cdc.gov/hantavirus/data-research/index.html",
        "https://emergency.cdc.gov/han/index.asp",
    ],
    "BBC": [
        "https://www.bbc.com/news/topics/hantavirus",
        "https://www.bbc.com/news/search?q=hantavirus+2026",
        "https://www.bbc.co.uk/news/health",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TRC-Dashboard-Bot/1.0; "
        "+https://trcresearchcollective-source.github.io)"
    )
}


def fetch(url, timeout=15):
    """Fetch a URL and return text, or None on failure."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fetch failed ({url}): {e}")
        return None


def extract_numbers(text):
    """
    Extract confirmed cases, deaths, and suspected cases from raw text.
    Returns dict with keys: confirmed, deaths, suspected (all int or None).
    """
    if not text:
        return {"confirmed": None, "deaths": None, "suspected": None}

    # Normalise whitespace
    text = re.sub(r"\s+", " ", text)

    confirmed = None
    deaths = None
    suspected = None

    # Patterns — look for a number near relevant keywords within ~60 chars
    # Confirmed cases
    for pat in [
        r"(\d+)\s*(?:laboratory[- ]?)?confirmed\s*(?:human\s*)?(?:case|infection|patient)",
        r"confirmed[^.]{0,60}?(\d+)\s*(?:case|patient|infection)",
        r"(\d+)\s*(?:PCR|lab)[- ]confirmed",
        r"total[^.]{0,40}?(\d+)\s*confirmed",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 500:  # sanity range
                confirmed = val
                break

    # Deaths / fatalities
    for pat in [
        r"(\d+)\s*(?:people\s*)?(?:have\s*)?(?:died|deaths?|fatalities|fatal)",
        r"(?:died|deaths?|fatalities|fatal)[^.]{0,60}?(\d+)",
        r"killed\s+(\d+)",
        r"(\d+)\s*(?:have\s*)?died",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 500:
                deaths = val
                break

    # Suspected cases
    for pat in [
        r"(\d+)\s*suspected\s*(?:case|patient|infection)",
        r"suspected[^.]{0,60}?(\d+)\s*(?:case|patient)",
        r"(?:probable|possible)[^.]{0,60}?(\d+)\s*(?:case|patient)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 500:
                suspected = val
                break

    return {"confirmed": confirmed, "deaths": deaths, "suspected": suspected}


def scrape_source(name, urls):
    """Try each URL for a source until we get useful data."""
    print(f"\n── {name} ──")
    for url in urls:
        print(f"  Trying: {url}")
        text = fetch(url)
        if not text:
            continue
        # Only process pages that mention hantavirus
        if "hantavirus" not in text.lower() and "hanta" not in text.lower():
            print(f"  No hantavirus mention — skipping")
            continue
        data = extract_numbers(text)
        print(f"  Extracted: {data}")
        if any(v is not None for v in data.values()):
            data["url"] = url
            return data
        print(f"  No numbers found — trying next URL")
    print(f"  No data found for {name}")
    return {"confirmed": None, "deaths": None, "suspected": None, "url": urls[0]}


# ── Run all scrapers ──────────────────────────────────────────────────────────
print("=" * 50)
print("Hantavirus Dashboard Scraper")
print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 50)

results = {}
for source_name, source_urls in SOURCES.items():
    results[source_name] = scrape_source(source_name, source_urls)

print("\n── Final results ──")
print(json.dumps(results, indent=2))

# ── Read existing index.html ──────────────────────────────────────────────────
with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()


def replace_marker(html, marker, value):
    pattern = rf"(<!-- {re.escape(marker)} -->)([^<]*)(<!-- /{re.escape(marker)} -->)"
    result, n = re.subn(pattern, rf"\g<1>{value}\g<3>", html)
    if n == 0:
        print(f"  Warning: marker {marker} not found")
    return result


# ── Build source panel HTML ───────────────────────────────────────────────────
def source_row(name, data, color):
    conf = data.get("confirmed", "—") or "—"
    dead = data.get("deaths", "—") or "—"
    susp = data.get("suspected", "—") or "—"
    url  = data.get("url", "#")
    return f"""
    <div class="src-row">
      <div class="src-name" style="color:{color};">{name}</div>
      <div class="src-stat"><span class="src-label">Confirmed</span><span class="src-val" style="color:{color};">{conf}</span></div>
      <div class="src-stat"><span class="src-label">Deaths</span><span class="src-val">{dead}</span></div>
      <div class="src-stat"><span class="src-label">Suspected</span><span class="src-val">{susp}</span></div>
      <a class="src-link" href="{url}" target="_blank" rel="noopener">↗ Source</a>
    </div>"""

source_panel_html = (
    source_row("WHO",  results["WHO"],  "#0e6565") +
    source_row("CDC",  results["CDC"],  "#43977e") +
    source_row("BBC",  results["BBC"],  "#61c07b")
)

# ── Determine best confirmed/deaths (WHO priority, fallback to others) ────────
def best(key):
    for src in ["WHO", "CDC", "BBC"]:
        v = results[src].get(key)
        if v is not None:
            return v
    return None

best_confirmed = best("confirmed")
best_deaths    = best("deaths")
best_suspected = best("suspected")

cfr = "—"
if best_confirmed and best_deaths and best_confirmed > 0:
    cfr = f"{round((best_deaths / best_confirmed) * 100)}%"

# ── Timestamps ────────────────────────────────────────────────────────────────
now = datetime.now(timezone.utc)
updated_str    = now.strftime("%-d %b %Y, %H:%MUTC")
updated_header = now.strftime("%d %b %Y")

# ── Inject values ─────────────────────────────────────────────────────────────
if best_confirmed:
    html = replace_marker(html, "CONFIRMED",    str(best_confirmed))
if best_suspected:
    html = replace_marker(html, "SUSPECTED",    str(best_suspected))
if best_deaths:
    html = replace_marker(html, "DEATHS",       str(best_deaths))

html = replace_marker(html, "CFR",          cfr)
html = replace_marker(html, "LAST_UPDATED", updated_str)
html = replace_marker(html, "HEADER_DATE",  f"Updated {updated_header}")
html = replace_marker(html, "SOURCE_PANEL", source_panel_html)

# ── Write ─────────────────────────────────────────────────────────────────────
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✓ Dashboard updated at {updated_str}")
print(f"  Confirmed: {best_confirmed} | Deaths: {best_deaths} | Suspected: {best_suspected} | CFR: {cfr}")
