"""
Hantavirus Dashboard Auto-Updater
Scrapes WHO and CDC only for MV Hondius outbreak data (April 2026-present).
No API key required — completely free to run.
"""

import re
import json
import urllib.request
from datetime import datetime, timezone

# ── Known baseline (last confirmed by WHO on 7 May 2026) ─────────────────────
BASELINE = {
    "confirmed": 5,
    "suspected": 3,
    "deaths": 3,
}

# ── Outbreak-specific sanity limits ──────────────────────────────────────────
MAX_CONFIRMED = 50   # if scraper finds more, it grabbed a historical total
MAX_DEATHS    = 20
MAX_SUSPECTED = 30

# ── URLs to scrape (WHO and CDC only) ────────────────────────────────────────
SOURCES = {
    "WHO": [
        "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON599",
        "https://www.who.int/emergencies/disease-outbreak-news",
        "https://www.who.int/news/item/07-05-2026-hantavirus",
    ],
    "CDC": [
        "https://www.cdc.gov/hantavirus/outbreaks/index.html",
        "https://www.cdc.gov/hantavirus/php/investigation/index.html",
        "https://www.cdc.gov/hantavirus/index.html",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TRC-Dashboard-Bot/1.0; "
        "+https://trcresearchcollective-source.github.io)"
    )
}

# ── Outbreak context keywords ─────────────────────────────────────────────────
OUTBREAK_CONTEXT = [
    "hondius", "cruise", "ship", "vessel", "outbreak", "cluster",
    "andes", "april 2026", "may 2026", "ushuaia", "don599",
]


def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fetch failed ({url}): {e}")
        return None


def has_outbreak_context(text):
    text_lower = text.lower()
    return any(kw in text_lower for kw in OUTBREAK_CONTEXT)


def extract_in_context(text, number_patterns, window=200):
    """Only return a number if it appears near an outbreak context keyword."""
    text_lower = text.lower()
    for pat in number_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            val = int(m.group(1))
            start = max(0, m.start() - window)
            end   = min(len(text), m.end() + window)
            snippet = text_lower[start:end]
            if any(kw in snippet for kw in OUTBREAK_CONTEXT):
                return val
    return None


def extract_numbers(text):
    if not text:
        return {"confirmed": None, "deaths": None, "suspected": None}

    text = re.sub(r"\s+", " ", text)

    confirmed = extract_in_context(text, [
        r"(\d+)\s*(?:laboratory[- ]?)?confirmed\s*(?:human\s*)?(?:case|infection|patient)",
        r"confirmed[^.]{0,60}?(\d+)\s*(?:case|patient|infection)",
        r"(\d+)\s*(?:PCR|lab)[- ]confirmed",
        r"total[^.]{0,40}?(\d+)\s*confirmed",
    ])

    deaths = extract_in_context(text, [
        r"(\d+)\s*(?:people\s*)?(?:have\s*)?(?:died|deaths?|fatalities|fatal)",
        r"(?:died|deaths?|fatalities)[^.]{0,60}?(\d+)",
        r"(\d+)\s*(?:have\s*)?died",
        r"killed\s+(\d+)",
    ])

    suspected = extract_in_context(text, [
        r"(\d+)\s*suspected\s*(?:case|patient|infection)",
        r"suspected[^.]{0,60}?(\d+)\s*(?:case|patient)",
        r"(?:probable|possible)[^.]{0,60}?(\d+)\s*(?:case|patient)",
    ])

    # Sanity checks
    if confirmed is not None and (confirmed < 1 or confirmed > MAX_CONFIRMED):
        print(f"  Confirmed {confirmed} outside range — discarding")
        confirmed = None
    if deaths is not None and (deaths < 1 or deaths > MAX_DEATHS):
        print(f"  Deaths {deaths} outside range — discarding")
        deaths = None
    if suspected is not None and (suspected < 1 or suspected > MAX_SUSPECTED):
        print(f"  Suspected {suspected} outside range — discarding")
        suspected = None
    if confirmed and deaths and deaths > confirmed:
        print(f"  Deaths ({deaths}) > confirmed ({confirmed}) — discarding deaths")
        deaths = None

    return {"confirmed": confirmed, "deaths": deaths, "suspected": suspected}


def scrape_source(name, urls):
    print(f"\n── {name} ──")
    for url in urls:
        print(f"  Trying: {url}")
        text = fetch(url)
        if not text:
            continue
        if "hantavirus" not in text.lower():
            print(f"  No hantavirus mention — skipping")
            continue
        if not has_outbreak_context(text):
            print(f"  No MV Hondius context — skipping (likely historical/general page)")
            continue
        data = extract_numbers(text)
        print(f"  Extracted: {data}")
        if any(v is not None for v in data.values()):
            data["url"] = url
            return data
        print(f"  No valid numbers — trying next URL")
    print(f"  No outbreak data found for {name} — will use baseline")
    return {"confirmed": None, "deaths": None, "suspected": None, "url": urls[0]}


# ── Run scrapers ──────────────────────────────────────────────────────────────
print("=" * 55)
print("Hantavirus Dashboard Scraper (WHO + CDC only)")
print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 55)

results = {}
for source_name, source_urls in SOURCES.items():
    results[source_name] = scrape_source(source_name, source_urls)

print("\n── Raw results ──")
print(json.dumps(results, indent=2))

# ── Merge: WHO first, CDC fills gaps, baseline fills rest ────────────────────
def best(key):
    for src in ["WHO", "CDC"]:
        v = results[src].get(key)
        if v is not None:
            return v, src
    return BASELINE[key], "WHO (baseline)"

best_confirmed, conf_src  = best("confirmed")
best_deaths,    death_src = best("deaths")
best_suspected, susp_src  = best("suspected")

print(f"\n── Final values ──")
print(f"  Confirmed: {best_confirmed} ({conf_src})")
print(f"  Deaths:    {best_deaths} ({death_src})")
print(f"  Suspected: {best_suspected} ({susp_src})")

cfr = "—"
if best_confirmed and best_deaths and best_confirmed > 0:
    cfr = f"{round((best_deaths / best_confirmed) * 100)}%"

now = datetime.now(timezone.utc)
updated_str    = now.strftime("%-d %b %Y, %H:%MUTC")
updated_header = now.strftime("%d %b %Y")

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()


def replace_marker(html, marker, value):
    pattern = rf"(<!-- {re.escape(marker)} -->)([^<]*)(<!-- /{re.escape(marker)} -->)"
    result, n = re.subn(pattern, rf"\g<1>{value}\g<3>", html)
    if n == 0:
        print(f"  Warning: marker {marker} not found")
    return result


def source_row(name, data, color):
    conf = data.get("confirmed") or "—"
    dead = data.get("deaths")    or "—"
    susp = data.get("suspected") or "—"
    url  = data.get("url", "#")
    note = "" if any(v != "—" for v in [conf, dead, susp]) else \
           "<div style='font-size:10px;color:#9a9589;margin-top:4px;'>No new update — showing baseline</div>"
    return f"""
    <div class="src-row">
      <div class="src-name" style="color:{color};">{name}</div>
      <div class="src-stat"><span class="src-label">Confirmed</span><span class="src-val" style="color:{color};">{conf}</span></div>
      <div class="src-stat"><span class="src-label">Deaths</span><span class="src-val">{dead}</span></div>
      <div class="src-stat"><span class="src-label">Suspected</span><span class="src-val">{susp}</span></div>
      <a class="src-link" href="{url}" target="_blank" rel="noopener">Source</a>
      {note}
    </div>"""

source_panel_html = (
    source_row("WHO", results["WHO"], "#0e6565") +
    source_row("CDC", results["CDC"], "#43977e")
)

html = replace_marker(html, "CONFIRMED",    str(best_confirmed))
html = replace_marker(html, "SUSPECTED",    str(best_suspected))
html = replace_marker(html, "DEATHS",       str(best_deaths))
html = replace_marker(html, "CFR",          cfr)
html = replace_marker(html, "LAST_UPDATED", updated_str)
html = replace_marker(html, "HEADER_DATE",  f"Updated {updated_header}")
html = replace_marker(html, "SOURCE_PANEL", source_panel_html)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nDashboard updated at {updated_str}")
print(f"Confirmed: {best_confirmed} | Deaths: {best_deaths} | Suspected: {best_suspected} | CFR: {cfr}")
