import anthropic
import json
import re
import os
from datetime import datetime, timezone

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Ask Claude to fetch latest hantavirus data ──────────────────────────────
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    messages=[{
        "role": "user",
        "content": """Search for the latest hantavirus outbreak data from WHO, CDC, or major news sources (CNN, BBC, Reuters, Al Jazeera).
Focus on the MV Hondius cruise ship outbreak from April 2026.

Return ONLY a JSON object with no other text, no markdown, no backticks:
{
  "confirmed_cases": <integer or null if not found>,
  "suspected_cases": <integer or null if not found>,
  "deaths": <integer or null if not found>,
  "countries_monitoring": <integer or null if not found>,
  "ship_status": "<current ship location/status string or null>",
  "who_risk_level": "<LOW, MEDIUM, HIGH, or null>",
  "latest_update_summary": "<one sentence summary of the most recent development, max 120 chars>",
  "source": "<name of the most authoritative source you found>"
}"""
    }]
)

# ── Extract text from response (may include tool use blocks) ────────────────
raw = ""
for block in response.content:
    if hasattr(block, "text"):
        raw += block.text

raw = raw.strip().replace("```json", "").replace("```", "").strip()

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("Could not parse JSON response — keeping existing dashboard.")
    print("Raw response:", raw)
    exit(0)

print("Fetched data:", json.dumps(data, indent=2))

# ── Validate we got useful data ─────────────────────────────────────────────
confirmed = data.get("confirmed_cases")
suspected = data.get("suspected_cases")
deaths = data.get("deaths")
countries = data.get("countries_monitoring")
ship_status = data.get("ship_status") or "En route Tenerife"
risk_level = data.get("who_risk_level") or "LOW"
summary = data.get("latest_update_summary") or ""
source = data.get("source") or "WHO / CDC"

if confirmed is None and deaths is None:
    print("No new data found — keeping existing dashboard.")
    exit(0)

# ── Compute CFR ──────────────────────────────────────────────────────────────
cfr = "—"
if confirmed and deaths and confirmed > 0:
    cfr = f"{round((deaths / confirmed) * 100)}%"

# ── Timestamp ───────────────────────────────────────────────────────────────
now = datetime.now(timezone.utc)
updated_str = now.strftime("%-d %b %Y, %H:%MUTC")
updated_header = now.strftime("%d %b %Y")

# ── Read existing index.html ─────────────────────────────────────────────────
with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

# ── Helper: replace a metric value between markers ──────────────────────────
def replace_metric(html, marker, new_value):
    pattern = rf'(<!-- {re.escape(marker)} -->)([^<]*)(<!-- /{re.escape(marker)} -->)'
    replacement = rf'\g<1>{new_value}\g<3>'
    result, count = re.subn(pattern, replacement, html)
    if count == 0:
        print(f"Warning: marker '{marker}' not found in HTML")
    return result

# ── Inject updated values ────────────────────────────────────────────────────
if confirmed is not None:
    html = replace_metric(html, "CONFIRMED", str(confirmed))
if suspected is not None:
    html = replace_metric(html, "SUSPECTED", str(suspected))
if deaths is not None:
    html = replace_metric(html, "DEATHS", str(deaths))
if countries is not None:
    html = replace_metric(html, "COUNTRIES", str(countries) + "+")

html = replace_metric(html, "CFR", cfr)
html = replace_metric(html, "SHIP_STATUS", ship_status)
html = replace_metric(html, "LAST_UPDATED", updated_str)
html = replace_metric(html, "HEADER_DATE", f"Updated {updated_header}")

if summary:
    html = replace_metric(html, "LATEST_SUMMARY", summary)

html = replace_metric(html, "DATA_SOURCE", source)

# ── Write updated file ───────────────────────────────────────────────────────
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard updated successfully at {updated_str}")
