"""
Hantavirus Dashboard Auto-Updater
Scrapes WHO, CDC, and CIDRAP for MV Hondius outbreak data.
Falls back to hardcoded baseline if scraping returns bad data.
No API key required.
"""

import re
import json
import urllib.request
from datetime import datetime, timezone

# ── Hardcoded baseline — last verified manually from WHO 15 May 2026 ──────────
# The scraper can only UPDATE these upward, never downward
BASELINE = {
    "confirmed": 10,   # 8 lab-confirmed + 2 probable = 10 total cases per WHO
    "suspected": 2,    # probable cases
    "deaths": 3,       # no new deaths since 2 May
}

# ── Tight sanity range for this specific outbreak ─────────────────────────────
MIN_CONFIRMED = 10    # we know it's at least 10
MAX_CONFIRMED = 100   # extremely unlikely to exceed this
MIN_DEATHS    = 3     # we know 3 people died
MAX_DEATHS    = 10    # deaths can't exceed confirmed cases realistically
MIN_SUSPECTED = 2
MAX_SUSPECTED = 50

# ── URLs ──────────────────────────────────────────────────────────────────────
SOURCES = {
    "WHO": [
        "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON599",
        "https://www.who.int/emergencies/disease-outbreak-news",
    ],
    "CDC": [
        "https://www.cdc.gov/hantavirus/outbreaks/index.html",
        "https://www.cdc.gov/hantavirus/php/investigation/index.html",
    ],
    "CIDRAP": [
        "https://www.cidrap.umn.edu/misc-emerging-topics/cdc-risk-general-public-hantavirus-low",
        "https://www.cidrap.umn.edu/misc-emerging-topics/hantavirus-outbreak-reduced-10-cases-ship-passengers-return-home-countries",
        "https://www.cidrap.umn.edu/misc-emerging-topics/hantavirus-outbreak-grows-11-cases-9-confirmed",
        "https://www.cidrap.umn.edu/misc-emerging-topics/more-hantavirus-cases-emerge-passengers-debark-cruise-ship",
        "https://www.cidrap.umn.edu/misc-emerging-topics/who-officials-hantavirus-cases-outbreak-ship-not-another-covid-19",
        "https://www.cidrap.umn.edu/misc-emerging-topics/least-8-sickened-suspected-hantavirus-outbreak-andes-strain-confirmed",
        "https://www.cidrap.umn.edu/misc-emerging-topics",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TRC-Dashboard-Bot/1.0; "
        "+https://trcresearchcollective-source.github.io)"
    )
}

OUTBREAK_CONTEXT = [
    "hondius", "cruise", "ship", "andes", "april 2026", "may 2026",
    "ushuaia", "don599", "tenerife", "mv hondius",
]


def fetch(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fetch failed ({url}): {e}")
        return None


def has_outbreak_context(text):
    tl = text.lower()
    return any(kw in tl for kw in OUTBREAK_CONTEXT)


def find_number_near_keyword(text, number_patterns, keyword_sets, window=250):
    """
    Return an integer only if:
    1. It matches one of the number_patterns (each must have one capture group)
    2. It appears within `window` chars of at least one keyword from keyword_sets
    3. It passes the sanity range check
    """
    tl = text.lower()
    for pat in number_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                val = int(m.group(1))
            except (IndexError, ValueError):
                continue
            start   = max(0, m.start() - window)
            end     = min(len(text), m.end() + window)
            snippet = tl[start:end]
            if any(kw in snippet for kw in keyword_sets):
                return val
    return None


def extract_numbers(text):
    if not text:
        return {}

    text = re.sub(r"\s+", " ", text)
    result = {}

    # ── Total / confirmed cases ───────────────────────────────────────────────
    # Must be near outbreak context AND in the right range
    raw_confirmed = find_number_near_keyword(text, [
        r"total\s*(?:of\s*)?(\d+)\s*cases",
        r"(\d+)\s*(?:laboratory[- ]?)?confirmed\s*(?:case|infection|patient)",
        r"confirmed[^.]{0,60}?(\d+)\s*(?:case|patient)",
        r"outbreak.*?(?:remains?|grown?|risen?|total).*?(\d+)\s*cases",
        r"(\d+)\s*cases.*?(?:reported|identified|linked to)",
    ], OUTBREAK_CONTEXT)

    if raw_confirmed is not None:
        if MIN_CONFIRMED <= raw_confirmed <= MAX_CONFIRMED:
            result["confirmed"] = raw_confirmed
        else:
            print(f"  Confirmed {raw_confirmed} outside [{MIN_CONFIRMED},{MAX_CONFIRMED}] — discarding")

    # ── Deaths ────────────────────────────────────────────────────────────────
    raw_deaths = find_number_near_keyword(text, [
        r"including\s*(\d+)\s*deaths",
        r"(\d+)\s*(?:people\s*)?(?:have\s*)?died",
        r"(\d+)\s*deaths?",
        r"killed\s+(\d+)",
        r"(\d+)\s*fatalities",
    ], OUTBREAK_CONTEXT)

    if raw_deaths is not None:
        if MIN_DEATHS <= raw_deaths <= MAX_DEATHS:
            result["deaths"] = raw_deaths
        else:
            print(f"  Deaths {raw_deaths} outside [{MIN_DEATHS},{MAX_DEATHS}] — discarding")

    # ── Probable / suspected ──────────────────────────────────────────────────
    raw_suspected = find_number_near_keyword(text, [
        r"(\d+)\s*probable",
        r"(\d+)\s*suspected\s*(?:case|patient|infection)",
        r"(?:probable|possible)[^.]{0,60}?(\d+)\s*(?:case|patient)",
    ], OUTBREAK_CONTEXT)

    if raw_suspected is not None:
        if MIN_SUSPECTED <= raw_suspected <= MAX_SUSPECTED:
            result["suspected"] = raw_suspected
        else:
            print(f"  Suspected {raw_suspected} outside [{MIN_SUSPECTED},{MAX_SUSPECTED}] — discarding")

    return result


def scrape_source(name, urls):
    print(f"\n── {name} ──")
    best = {}
    for url in urls:
        print(f"  Trying: {url}")
        text = fetch(url)
        if not text or not has_outbreak_context(text):
            print(f"  Skipped (no outbreak context or fetch failed)")
            continue
        data = extract_numbers(text)
        print(f"  Extracted: {data}")
        # Keep whichever result has more fields
        if len(data) > len(best):
            best = data
            best["url"] = url
        if len(best) >= 3:
            break
    if not best:
        print(f"  No valid data — will use baseline")
    return best


# ── Run ───────────────────────────────────────────────────────────────────────
print("=" * 60)
print("Hantavirus Dashboard Scraper — WHO + CDC + CIDRAP")
print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 60)

results = {}
for name, urls in SOURCES.items():
    results[name] = scrape_source(name, urls)

print("\n── Raw scraped results ──")
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "url"}
                  for k, v in results.items()}, indent=2))

# ── Merge: WHO → CIDRAP → CDC → baseline ─────────────────────────────────────
# Never go below baseline — only accept values >= baseline minimums
def best_value(key):
    for src in ["WHO", "CIDRAP", "CDC"]:
        v = results[src].get(key)
        if v is not None:
            return v, src
    return BASELINE[key], "baseline"

confirmed, conf_src  = best_value("confirmed")
deaths,    death_src = best_value("deaths")
suspected, susp_src  = best_value("suspected")

# Final sanity: deaths must not exceed confirmed
if deaths > confirmed:
    print(f"  Deaths ({deaths}) > confirmed ({confirmed}) — resetting deaths to baseline")
    deaths = BASELINE["deaths"]
    death_src = "baseline"

cfr = f"{round((deaths / confirmed) * 100)}%" if confirmed > 0 else "—"

print(f"\n── Final values ──")
print(f"  Confirmed: {confirmed} ({conf_src})")
print(f"  Deaths:    {deaths} ({death_src})")
print(f"  Probable:  {suspected} ({susp_src})")
print(f"  CFR:       {cfr}")

now            = datetime.now(timezone.utc)
updated_str    = now.strftime("%-d %b %Y, %H:%MUTC")
updated_header = now.strftime("%d %b %Y")

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()


def replace_marker(html, marker, value):
    pattern = rf"(<!-- {re.escape(marker)} -->)([^<]*)(<!-- /{re.escape(marker)} -->)"
    result, n = re.subn(pattern, rf"\g<1>{value}\g<3>", html)
    if n == 0:
        print(f"  Warning: marker '{marker}' not found in HTML")
    return result


def source_row(name, data, color):
    conf = data.get("confirmed", "—")
    dead = data.get("deaths", "—")
    susp = data.get("suspected", "—")
    url  = data.get("url", "#")
    note = "" if any(k in data for k in ["confirmed","deaths","suspected"]) else \
           "<div style='font-size:10px;color:#9a9589;margin-top:4px;'>No new data — baseline shown</div>"
    return f"""
    <div class="src-row">
      <div class="src-name" style="color:{color};">{name}</div>
      <div class="src-stat"><span class="src-label">Cases</span><span class="src-val" style="color:{color};">{conf}</span></div>
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

html = replace_marker(html, "CONFIRMED",    str(confirmed))
html = replace_marker(html, "SUSPECTED",    str(suspected))
html = replace_marker(html, "DEATHS",       str(deaths))
html = replace_marker(html, "CFR",          cfr)
html = replace_marker(html, "LAST_UPDATED", updated_str)
html = replace_marker(html, "HEADER_DATE",  f"Updated {updated_header}")
html = replace_marker(html, "SOURCE_PANEL", source_panel_html)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✓ Dashboard updated at {updated_str}")
