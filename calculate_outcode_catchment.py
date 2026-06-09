"""
calculate_outcode_catchment.py
==============================
Allocates ONS population (Census 2021) and ONS live births (2016-2018) to
hospitals using the outcode-based catchment defined in docs/outcode_map.json.

Split method: postcode-count weighted
  For each outcode that maps to N hospitals, the outcode's population/births
  are shared in proportion to how many *full postcodes* from that outcode
    each hospital already owns in output/analysis/All_Postcodes.csv (any-level routing).
  If none of the listed hospitals own any postcodes from that outcode (e.g.
  non-residential outcodes like EC1P), the outcode's value is split equally.

Outputs
-------
  output/Outcode_Catchment_Populations.csv
  output/Outcode_Catchment_Births.csv
  docs/outcode_populations.json
  docs/outcode_births.json
"""

import csv, json, re, collections, openpyxl

# ── 1. Load outcode → hospitals mapping ────────────────────────────────────
with open("docs/outcode_map.json", encoding="utf-8") as f:
    outcode_map = json.load(f)["outward_to_hospitals"]   # {outcode: [hosp, ...]}

all_hospitals = sorted({h for hs in outcode_map.values() for h in hs})

# ── 2. Build postcode-count weights from output/analysis/All_Postcodes.csv ──
# outcode_any_counts[outcode][hospital] = # postcodes routed there at Any level
outcode_any_counts = collections.defaultdict(lambda: collections.defaultdict(int))

with open("output/analysis/All_Postcodes.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        pc = row["Postcode"].replace(" ", "").upper()
        outcode = pc[:-3]          # everything except last 3 chars
        hosp = row["Closest_Any"]
        outcode_any_counts[outcode][hosp] += 1

def get_weights(outcode, hospitals):
    """
    Returns a dict {hospital: weight} that sums to 1.0,
    based on postcode-count share within the listed hospitals for that outcode.
    Falls back to equal split if no counts are found.
    """
    counts = {h: outcode_any_counts[outcode].get(h, 0) for h in hospitals}
    total = sum(counts.values())
    if total == 0:
        n = len(hospitals)
        return {h: 1.0/n for h in hospitals}
    return {h: counts[h]/total for h in hospitals}

# ── 3. Load ONS Census 2021 population (pcd_p001.csv) ──────────────────────
def normalise_postcode(pc):
    pc = pc.replace(" ", "").upper()
    return pc[:-3] + " " + pc[-3:]

postcode_pop = collections.defaultdict(int)
with open("pcd_p001.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        pc = normalise_postcode(row["Postcode"])
        try:
            postcode_pop[pc] += int(row["Count"])
        except (ValueError, KeyError):
            pass

# Sum population per outcode
outcode_pop = collections.defaultdict(int)
for pc, pop in postcode_pop.items():
    oc = pc.replace(" ", "")[:-3]
    outcode_pop[oc] += pop

# ── 4. Load ONS births by postcode sector (birthsbypcdfinal.xlsx) ──────────
def sector_from_outcode(outcode):
    """Return all sectors that could belong to this outcode.
    Sector = outcode + ' ' + first digit of inward.
    We collect all 10 possible: outcode + ' 0' .. outcode + ' 9'.
    """
    return [f"{outcode} {d}" for d in "0123456789"]

wb = openpyxl.load_workbook("birthsbypcdfinal.xlsx", read_only=True, data_only=True)
sheet = wb["Table 4"]

sector_births = {}
for row in sheet.iter_rows(values_only=True):
    if not row[0]:
        continue
    cell = str(row[0]).strip().upper()
    # Sector pattern: e.g. "SW1A 1"
    if re.match(r'^[A-Z]{1,2}\d[A-Z\d]?\s+\d$', cell):
        try:
            val = float(row[3]) if row[3] is not None else 0   # col 3 = Total births
            sector_births[cell] = sector_births.get(cell, 0) + val
        except (TypeError, ValueError):
            pass

wb.close()

# Sum births per outcode across all its sectors
outcode_births = collections.defaultdict(float)
for oc in outcode_map:
    for sec in sector_from_outcode(oc):
        outcode_births[oc] += sector_births.get(sec, 0)

# ── 5. Allocate to hospitals ───────────────────────────────────────────────
hosp_pop    = collections.defaultdict(float)
hosp_births = collections.defaultdict(float)

for outcode, hospitals in outcode_map.items():
    if not hospitals:
        continue
    weights = get_weights(outcode, hospitals)
    pop = outcode_pop.get(outcode, 0)
    births = outcode_births.get(outcode, 0)
    for h, w in weights.items():
        hosp_pop[h]    += pop * w
        hosp_births[h] += births * w

# ── 6. Write outputs ───────────────────────────────────────────────────────
pop_rows    = [{"hospital": h, "population": round(hosp_pop.get(h, 0))}    for h in all_hospitals]
births_rows = [{"hospital": h, "births":     round(hosp_births.get(h, 0))} for h in all_hospitals]

with open("output/Outcode_Catchment_Populations.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["hospital", "population"])
    w.writeheader(); w.writerows(pop_rows)

with open("output/Outcode_Catchment_Births.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["hospital", "births"])
    w.writeheader(); w.writerows(births_rows)

with open("docs/outcode_populations.json", "w", encoding="utf-8") as f:
    json.dump(pop_rows, f, separators=(',', ':'))

with open("docs/outcode_births.json", "w", encoding="utf-8") as f:
    json.dump(births_rows, f, separators=(',', ':'))

# ── 7. Summary ────────────────────────────────────────────────────────────
print("=== Outcode Catchment Populations ===")
for r in sorted(pop_rows, key=lambda x: -x["population"])[:10]:
    print(f"  {r['hospital']:<35} {r['population']:>10,}")

print("\n=== Outcode Catchment Births ===")
for r in sorted(births_rows, key=lambda x: -x["births"])[:10]:
    print(f"  {r['hospital']:<35} {r['births']:>10,}")

print(f"\nTotal population : {sum(r['population'] for r in pop_rows):,}")
print(f"Total births     : {sum(r['births'] for r in births_rows):,}")
print("\nDone.")
