"""
Hantavirus Dashboard Auto-Updater
Scrapes WHO, CDC, and CIDRAP for MV Hondius outbreak data (April 2026-present).
No API key required — completely free to run.
"""

import re
import json
import urllib.request
from datetime import datetime, timezone

# ── Known baseline (WHO 15 May 2026 briefing) ────────────────────────────────
BASELINE = {
    "confirmed": 8,
    "suspected": 2,
    "deaths": 3,
}

# ── Sanity limits ─────────────────────────────────────────────────────────────
MAX_CONFIRMED = 200
MAX_DEATHS    = 50
MAX_SUSPECTED = 100

# ── Outbreak context keywords ─────────────────────────────────────────────────
OUTBREAK_CONTEXT = [
    "hondius", "cruise", "ship", "vessel", "outbreak", "cluster",
    "andes", "april 2026", "may 2026", "ushuaia", "don599", "tenerife",
    "mv hondius", "hantavirus",
]

# ── URLs — ordered most-recent-first within each source ──────────────────────
SOURCES = {
    "WHO": [
        # DG briefings (most current)
        "https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing---15-may-2026",
        "https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing---7-may-2026",
        # Disease Outbreak Notices
        "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON599",
        # Speeches index (catches future briefings automatically)
        "https://www.who.int/news-room/speeches",
        "https://www.who.int/emergencies/disease-outbreak-news",
    ],
    "CDC": [
        "https://www.cdc.gov/hantavirus/outbreaks/index.html",
        "https://www.cdc.gov/hantavirus/php/investigation/index.html",
        "https://emergency.cdc.gov/han/index.asp",
        "https://www.cdc.gov/hantavirus/index.html",
    ],
    "CIDRAP": [
        # Most recent articles first — new articles added here as they publish
        "https://www.cidrap.umn.edu/misc-emerging-topics/cdc-risk-general-public-hantavirus-low",
        "https://www.cidrap.umn.edu/misc-emerging-topics/hantavirus-outbreak-reduced-10-cases-ship-passengers-return-home-countries",
        "https://www.cidrap.umn.edu/misc-emerging-topics/hantavirus-outbreak-grows-11-cases-9-confirmed",
        "https://www.cidrap.umn.edu/misc-emerging-topics/osterholm-hantavirus-we-re-missing-main-point-outbreak",
        "https://www.cidrap.umn.edu/misc-emerging-topics/more-hantavirus-cases-emerge-passengers-debark-cruise-ship",
        "https://www.cidrap.umn.edu/misc-emerging-topics/who-officials-hantavirus-cases-outbreak-ship-not-another-covid-19",
        "https://www.cidrap.umn.edu/misc-emerging-topics/least-8-sickened-suspected-hantavirus-outbreak-andes-strain-confirmed",
        "https://www.cidrap.umn.edu/misc-emerging-topics/more-details-emerge-hantavirus-patients-cruise-ship",
        # CIDRAP topic index — catches new articles automatically
        "https://www.cidrap.umn.edu/misc-emerging-topics",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TRC-Dashboard-Bot/1.0; "
        "+https://trcresearchcollective-source.github.io)"
    )
}


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


def extract_in_context(text, number_patterns, window=300):
    """Only return a number appearing within `window` chars of an outbreak keyword."""
    text_lower = text.lower()
    for pat in number_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            val   = int(m.group(1))
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

    # ── Confirmed / lab-confirmed ─────────────────────────────────────────────
    confirmed = extract_in_context(text, [
        r"(\d+)\s*people\s*who\s*were\s*laboratory[- ]confirmed",
        r"(\d+)\s*(?:were\s*)?laboratory[- ]confirmed",
        r"(\d+)\s*(?:have\s*been\s*)?(?:laboratory[- ]?)?confirmed",
        r"confirmed[^.]{0,80}?(\d+)\s*(?:case|patient|infection)",
        r"(\d+)\s*(?:PCR|lab)[- ]confirmed",
        r"nine.*?(?:lab|laboratory)[- ]confirmed",   # "nine of which are confirmed"
        r"(\d+).*?(?:lab|laboratory)[- ]confirmed",
    ])

    # word-to-digit fallback for spelled-out numbers near "confirmed"
    if confirmed is None:
        word_map = {"one":1,"two":2,"three":3,"four":4,"five":5,
                    "six":6,"seven":7,"eight":8,"nine":9,"ten":10,
                    "eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15}
        for word, digit in word_map.items():
            pat = rf"{word}\s*(?:people\s*who\s*were\s*)?(?:laboratory[- ]?)?confirmed"
            if re.search(pat, text, re.IGNORECASE):
                # check outbreak context around match
                m = re.search(pat, text, re.IGNORECASE)
                start = max(0, m.start() - 300)
                end   = min(len(text), m.end() + 300)
                snippet = text[start:end].lower()
                if any(kw in snippet for kw in OUTBREAK_CONTEXT):
                    confirmed = digit
                    break

    # ── Total cases fallback ──────────────────────────────────────────────────
    total_cases = extract_in_context(text, [
        r"total\s*(?:of\s*)?(\d+)\s*cases",
        r"outbreak.*?(?:remains?|grows?|rises?|total).*?(\d+)\s*cases",
        r"(\d+)\s*cases.*?(?:reported|confirmed|identified|detected)",
        r"(?:reported|identified|detected)\s*(\d+)\s*cases",
        r"raised.*?outbreak.*?total.*?(\d+)\s*cases",
        r"outbreak.*?total.*?(\d+)\s*cases",
    ])

    # ── Deaths ────────────────────────────────────────────────────────────────
    deaths = extract_in_context(text, [
        r"including\s*(\d+)\s*deaths",
        r"killed\s+(\d+)",
        r"(\d+)\s*(?:have\s*)?died",
        r"(\d+)\s*deaths?",
        r"death\s*toll.*?(\d+)",
        r"(\d+)\s*fatalities",
    ])

    # ── Suspected / probable ──────────────────────────────────────────────────
    suspected = extract_in_context(text, [
        r"(\d+)\s*probable",
        r"two\s*probable",   # text match for "two probable"
        r"(\d+)\s*suspected\s*(?:case|patient|infection)",
        r"suspected[^.]{0,80}?(\d+)\s*(?:case|patient)",
        r"(?:probable|possible)[^.]{0,80}?(\d+)\s*(?:case|patient)",
    ])
    # word-to-digit for "two probable" etc.
    if suspected is None:
        for word, digit in {"two":2,"three":3,"four":4,"five":5,"one":1}.items():
            if re.search(rf"{word}\s*probable", text, re.IGNORECASE):
                suspected = digit
                break

    # ── Use total as confirmed if confirmed not found separately ──────────────
    if confirmed is None and total_cases is not None:
        print(f"  Using total_cases ({total_cases}) as confirmed fallback")
        confirmed = total_cases

    # ── Sanity checks ─────────────────────────────────────────────────────────
    if confirmed is not None and (confirmed < 1 or confirmed > MAX_CONFIRMED):
        print(f"  Confirmed {confirmed} out of range — discarding")
        confirmed = None
    if deaths is not None and (deaths < 1 or deaths > MAX_DEATHS):
        print(f"  Deaths {deaths} out of range — discarding")
        deaths = None
    if suspected is not None and (suspected < 1 or suspected > MAX_SUSPECTED):
        print(f"  Suspected {suspected} out of range — discarding")
        suspected = None

    return {"confirmed": confirmed, "deaths": deaths, "suspected": suspected}


def scrape_source(name, urls):
    print(f"\n── {name} ──")
    best_data  = {"confirmed": None, "deaths": None, "suspected": None, "url": urls[0]}
    best_score = 0
    for url in urls:
        print(f"  Trying: {url}")
        text = fetch(url)
        if not text:
            continue
        if not has_outbreak_context(text):
            print(f"  No MV Hondius context — skipping")
            continue
        data = extract_numbers(text)
        print(f"  Extracted: {data}")
        score = sum(1 for k, v in data.items() if v is not None)
        if score > best_score:
            best_score = score
            data["url"] = url
            best_data  = data
        if best_score == 3:
            break   # found confirmed + deaths + suspected — stop early
    if best_score == 0:
        print(f"  No data found for {name} — will use baseline")
    return best_data


# ── Run all scrapers ──────────────────────────────────────────────────────────
print("=" * 60)
print("Hantavirus Dashboard Scraper — WHO + CDC + CIDRAP")
print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 60)

results = {}
for source_name, source_urls in SOURCES.items():
    results[source_name] = scrape_source(source_name, source_urls)

print("\n── Raw results ──")
print(json.dumps(results, indent=2))

# ── Merge: WHO → CIDRAP → CDC → baseline ─────────────────────────────────────
def best(key):
    for src in ["WHO", "CIDRAP", "CDC"]:
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
print(f"  Probable:  {best_suspected} ({susp_src})")

cfr = "—"
if best_confirmed and best_deaths and best_confirmed > 0:
    cfr = f"{round((best_deaths / best_confirmed) * 100)}%"

now            = datetime.now(timezone.utc)
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
      <div class="src-stat"><span class="src-label">Probable</span><span class="src-val">{susp}</span></div>
      <a class="src-link" href="{url}" target="_blank" rel="noopener">Source</a>
      {note}
    </div>"""

source_panel_html = (
    source_row("WHO",    results["WHO"],    "#0e6565") +
    source_row("CIDRAP", results["CIDRAP"], "#43977e") +
    source_row("CDC",    results["CDC"],    "#61c07b")
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

print(f"\n✓ Dashboard updated at {updated_str}")
print(f"  Confirmed: {best_confirmed} | Deaths: {best_deaths} | Probable: {best_suspected} | CFR: {cfr}")
