"""
extract_outcode_json.py
Parses outwardToUnits from 'Outcode approach.html' and writes docs/outcode_map.json.
Also normalises abbreviated hospital names to match hospitals_refined.csv.
"""
import re, json

# ---------------------------------------------------------------------------
# Name mapping: abbreviations in Outcode approach.html → hospitals_refined.csv
# ---------------------------------------------------------------------------
NAME_MAP = {
    "PRUH":                  "Princess Royal (PRUH)",
    "QEW":                   "Queen Elizabeth Woolwich",
    "Croydon":               "Croydon University",
    "St. Helier":            "St Heliers Hospital",
    "Epsom":                 "Epsom Hospital",
    "Royal London":          "The Royal London",
    "Newham":                "Newham General",
    "Whipps Cross":          "Whipps Cross",
    "Homerton":              "Homerton University",
    "Barnet":                "Barnet Hospital",
    "North Middlesex":       "North Middlesex",
    "Royal Free":            "Royal Free Hospital",
    "UCLH":                  "UCH (University College)",
    "UCH":                   "UCH (University College)",
    "St. Mary's":            "St Marys Hospital",
    "Queen Charlotte's":     "Queen Charlottes'",
    "Northwick Park":        "Northwick Park",
    "Hillingdon":            "Hillingdon Hospital",
    "West Middlesex":        "West Middlesex",
    "Kingston":              "Kingston Hospital",
    "Queen's Romford":       "Queens Hospital",
    "GSTT":                  "Evelina (St Thomas')",
    "King's":                "Kings College Hospital",
    "Lewisham":              "University Lewisham",
    "Chelsea & Westminster": "Chelsea & Westminster",
    "St. George's":          "St. Georges Hospital",
    # typos / variants in the HTML
    "Whittingdon":           "Whittington Hospital",
    "Whittindon":            "Whittington Hospital",
    "Whittington":           "Whittington Hospital",
    # skip
    "outside London Neonatal Network": None,
}

# ---------------------------------------------------------------------------
# Parse the JS object from the HTML
# ---------------------------------------------------------------------------
with open("Outcode approach.html", encoding="utf-8") as f:
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
