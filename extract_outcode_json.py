"""
extract_outcode_json.py
Parses outwardToUnits from 'Outcode approach.html' and writes docs/outcode_map.json.

Hospital names come from hospitals_refined.csv (the single source of truth):
  * the "Aliases" column (semicolon-separated) lists the short names used in the
    outcode guide;
  * the "Level" column is written back into the guide's `units` list so the
    guide can never disagree with the CSV about a hospital's level.
"""
import re, json

import pandas as pd

HOSPITALS_CSV = "hospitals_refined.csv"
GUIDE_HTML    = "Outcode approach.html"

# ---------------------------------------------------------------------------
# Name mapping: aliases (from the CSV) -> canonical hospital name
# ---------------------------------------------------------------------------
hospitals = pd.read_csv(HOSPITALS_CSV)
hospitals.columns = hospitals.columns.str.strip()
hospitals["Hospital Name"] = hospitals["Hospital Name"].str.strip()

NAME_MAP = {}
for _, row in hospitals.iterrows():
    aliases = [] if pd.isna(row["Aliases"]) else [a.strip() for a in str(row["Aliases"]).split(";") if a.strip()]
    for alias in aliases + [row["Hospital Name"]]:
        if NAME_MAP.setdefault(alias, row["Hospital Name"]) != row["Hospital Name"]:
            raise ValueError(f"Alias '{alias}' is used by more than one hospital in {HOSPITALS_CSV}")

# Typos / variants that appear in the guide but are not worth a CSV alias
NAME_MAP.update({
    "Whittingdon": "Whittington Hospital",
    "Whittindon":  "Whittington Hospital",
    "Whittington": "Whittington Hospital",
    # skip
    "outside London Neonatal Network": None,
})

# ---------------------------------------------------------------------------
# Parse the JS object from the HTML
# ---------------------------------------------------------------------------
with open(GUIDE_HTML, encoding="utf-8") as f:
    html = f.read()

# Extract the JS object literal between 'const outwardToUnits = {' and '};'
m = re.search(r'const outwardToUnits\s*=\s*(\{.*?\});', html, re.DOTALL)
if not m:
    raise ValueError("Could not find outwardToUnits in HTML")

# Convert JS array syntax to valid JSON
js_obj = m.group(1)
# JS uses single-quoted strings? No — check. Actually it uses double-quoted already.
# Just eval via json after minor fixup (trailing commas)
js_obj_fixed = re.sub(r',\s*\}', '}', js_obj)   # remove trailing commas before }
js_obj_fixed = re.sub(r',\s*\]', ']', js_obj_fixed)

raw = json.loads(js_obj_fixed)

# ---------------------------------------------------------------------------
# Normalise hospital names, drop 'outside London Neonatal Network'
# ---------------------------------------------------------------------------
normalised = {}
unknown = set()
for outcode, abbrevs in raw.items():
    mapped = []
    for a in abbrevs:
        if a not in NAME_MAP:
            unknown.add(a)
            continue
        full = NAME_MAP[a]
        if full is not None:
            mapped.append(full)
    normalised[outcode] = mapped

if unknown:
    print(f"WARNING: unmapped names: {unknown}")

# ---------------------------------------------------------------------------
# Keep the guide's `units` levels in step with the CSV
# ---------------------------------------------------------------------------
level_by_name = dict(zip(hospitals["Hospital Name"], hospitals["Level"].astype(int)))

def _sync_level(match):
    block = match.group(0)
    alias_list = re.search(r'aliases:\s*\[(.*?)\]', block)
    aliases = re.findall(r'"([^"]+)"', alias_list.group(1)) if alias_list else []
    canon = {NAME_MAP[a] for a in aliases if NAME_MAP.get(a)}
    if len(canon) != 1:
        return block                      # not a hospital we can identify (e.g. GOSH)
    level = level_by_name[canon.pop()]
    return re.sub(r'level:\s*\d', f'level: {level}', block, count=1)

synced = re.sub(r'\{\s*name:\s*"[^"]+",\s*aliases:.*?mapUrl:[^\n]*\n\s*\}', _sync_level, html, flags=re.DOTALL)
if synced != html:
    with open(GUIDE_HTML, "w", encoding="utf-8") as f:
        f.write(synced)
    print(f"Updated unit levels in {GUIDE_HTML} from {HOSPITALS_CSV}")

# ---------------------------------------------------------------------------
# Write JSON
# ---------------------------------------------------------------------------
out = {"outward_to_hospitals": normalised}
with open("docs/outcode_map.json", "w", encoding="utf-8") as f:
    json.dump(out, f, separators=(',', ':'))

print(f"Written docs/outcode_map.json  ({len(normalised)} outcodes)")
unique_hosp = sorted({h for hs in normalised.values() for h in hs})
print(f"Unique hospitals: {len(unique_hosp)}")
for h in unique_hosp:
    print(f"  {h}")
