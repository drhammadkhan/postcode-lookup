#!/usr/bin/env python3
"""
build_comparison_page.py

Generates docs/comparison.html — two synced Leaflet maps side by side:
  LEFT:  Pure geographic Voronoi (nearest hospital, no equalisation)
  RIGHT: Population-equalised catchments (from equalise_catchments.py)

Also writes docs/comparison_dots.json — compact dot array for both maps:
  [[lat, lon, voronoi_idx, equalised_idx], ...]
"""

import json
import pandas as pd
import numpy as np
from shapely.geometry import Polygon, Point

from hospital_profiles import load_hospitals_for_profile

# ── Inputs ─────────────────────────────────────────────────────────────────────
ALL_CSV       = "output/analysis/All_Postcodes.csv"
EQUALISED_CSV = "output/All_Postcodes_Equalised.csv"
SUMMARY_CSV   = "output/Equalised_Summary.csv"
HOSPITALS_CSV = "hospitals_refined.csv"
OUTPUT_HTML   = "docs/comparison.html"
OUTPUT_DOTS   = "docs/comparison_dots.json"
SAMPLE_RATE   = 5

# ── Colour palette ─────────────────────────────────────────────────────────────
SECTOR_RANGES = {
    'NC':     {'h': (210, 235), 's': (80, 90),  'l': (22, 72)},
    'NE':     {'h': (108, 145), 's': (72, 88),  'l': (20, 68)},
    'NW':     {'h': (268, 308), 's': (68, 85),  'l': (22, 70)},
    'SE':     {'h': (18,  44),  's': (82, 95),  'l': (28, 70)},
    'SW':     {'h': (328, 354), 's': (68, 88),  'l': (32, 74)},
    'Border': {'h': (22,  40),  's': (45, 60),  'l': (22, 62)},
}
SECTOR_ORDER = ['NC', 'NE', 'NW', 'SE', 'SW', 'Border']
SECTOR_NORM  = {'South East': 'SE', 'South West': 'SW'}

def normalise_sector(raw):
    s = str(raw).strip() if pd.notna(raw) else 'Border'
    return SECTOR_NORM.get(s, s) if s in {*SECTOR_NORM, *SECTOR_RANGES} else 'Border'

def interleaved_order(n):
    order, lo, hi = [], 0, n - 1
    while lo <= hi:
        order.append(lo); lo += 1
        if lo <= hi: order.append(hi); hi -= 1
    return order

def hsl_str(h, s, l):
    return f'hsl({h},{s}%,{l}%)'

# ── Thames polygon (for map suppression) ──────────────────────────────────────
SOUTH_OF_THAMES = Polygon([
    (-0.51, 51.30), (0.35, 51.30), (0.35, 51.52),
    (0.10, 51.50),  (0.02, 51.48), (-0.02, 51.47),
    (-0.10, 51.46), (-0.20, 51.47),(-0.30, 51.46),
    (-0.40, 51.46), (-0.51, 51.47),(-0.51, 51.30),
])

MAP_SUPPRESS = {'SW97RT'}

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading data …")
base = pd.read_csv(ALL_CSV)
eq   = pd.read_csv(EQUALISED_CSV)
summ = pd.read_csv(SUMMARY_CSV)
hosp_df = load_hospitals_for_profile(HOSPITALS_CSV, profile="analysis")
hosp_df["Hospital Name"] = hosp_df["Hospital Name"].str.strip()

hosp_info = hosp_df.groupby("Hospital Name", as_index=False).first().set_index("Hospital Name")

# Merge equalised assignment onto base
merged = base.copy()
merged["New_Hospital"] = merged["Postcode"].map(
    eq.set_index("Postcode")["New_Hospital"]
)

# ── Colour map ─────────────────────────────────────────────────────────────────
all_hospitals = sorted(merged["Closest_Any"].dropna().unique())

sector_hospitals = {sec: [] for sec in SECTOR_ORDER}
for h in all_hospitals:
    sec = normalise_sector(hosp_info.loc[h, "Sector"]) if h in hosp_info.index else "Border"
    sector_hospitals[sec].append(h)

colour_map = {}
for sec in SECTOR_ORDER:
    hosps = sector_hospitals[sec]
    if not hosps:
        continue
    r = SECTOR_RANGES[sec]
    n = len(hosps)
    h_vals = np.linspace(r['h'][0], r['h'][1], n)
    s_vals = np.linspace(r['s'][0], r['s'][1], n)
    l_vals = np.linspace(r['l'][0], r['l'][1], n)
    order  = interleaved_order(n)
    for rank, hi in enumerate(order):
        colour_map[hosps[hi]] = hsl_str(int(h_vals[rank]), int(s_vals[rank]), int(l_vals[rank]))

# ── Hospital metadata ──────────────────────────────────────────────────────────
print("Building hospital metadata …")
hosp_names = all_hospitals
hosp_idx_map = {h: i for i, h in enumerate(hosp_names)}

summ_indexed = summ.set_index("Hospital")

def get_summ_val(name, col, agg="sum"):
    if name not in summ_indexed.index:
        return 0
    val = summ_indexed.loc[name, col]
    if hasattr(val, agg):
        return getattr(val, agg)()
    return val

hospitals_js = []
for name in hosp_names:
    colour = colour_map.get(name, '#888')
    info   = hosp_info.loc[name] if name in hosp_info.index else None

    # Voronoi postcode count
    vor_count = int((merged["Closest_Any"] == name).sum())

    # Equalised stats
    eq_pop    = int(get_summ_val(name, "Assigned_Weight"))
    eq_target = int(float(get_summ_val(name, "Target"))) if name in summ_indexed.index else 0
    eq_pct    = round(float(summ_indexed.loc[name, "Pct_vs_Target"].iloc[0]
                            if hasattr(summ_indexed.loc[name, "Pct_vs_Target"], "iloc")
                            else summ_indexed.loc[name, "Pct_vs_Target"]), 1) if name in summ_indexed.index else 0
    eq_count  = int(get_summ_val(name, "Postcode_Count"))

    hospitals_js.append({
        "name":           name,
        "lat":            round(float(info["Latitude"]),  4) if info is not None else None,
        "lon":            round(float(info["Longitude"]), 4) if info is not None else None,
        "level":          int(info["Level"])   if info is not None else None,
        "side":           str(info["Side"])    if info is not None else "Both",
        "color":          colour,
        "vor_count":      vor_count,
        "eq_population":  eq_pop,
        "eq_target":      eq_target,
        "eq_pct_dev":     eq_pct,
        "eq_count":       eq_count,
    })

# ── Sample dots ────────────────────────────────────────────────────────────────
print("Sampling postcodes …")
pc_norm = merged["Postcode"].str.replace(" ", "", regex=False)
clean = merged[
    merged["Latitude"].notna() &
    merged["Longitude"].notna() &
    merged["Closest_Any"].notna() &
    merged["New_Hospital"].notna() &
    ~pc_norm.isin(MAP_SUPPRESS)
].copy()

# Cluster filter (keep only high-density areas)
from scipy.spatial import cKDTree
xy = clean[["Latitude", "Longitude"]].values
tree = cKDTree(xy)
counts = tree.query_ball_point(xy, r=0.01, return_length=True)
clean = clean[counts >= 5].reset_index(drop=True)

sampled = clean.iloc[::SAMPLE_RATE].copy()

dots = [
    [round(r.Latitude, 4), round(r.Longitude, 4),
     hosp_idx_map.get(r.Closest_Any, -1),
     hosp_idx_map.get(r.New_Hospital, -1)]
    for r in sampled.itertuples()
    if r.Closest_Any in hosp_idx_map and r.New_Hospital in hosp_idx_map
]

print(f"  {len(dots):,} map dots")
with open(OUTPUT_DOTS, "w") as f:
    json.dump(dots, f, separators=(",", ":"))
size_kb = len(open(OUTPUT_DOTS).read()) / 1024
print(f"  Dots JSON → {OUTPUT_DOTS}  ({size_kb:.0f} KB)")

# ── Compute Voronoi population for popup ──────────────────────────────────────
pop_by_hosp_vor = merged.groupby("Closest_Any")["population"].sum().to_dict() \
    if "population" in merged.columns else {}
for h in hospitals_js:
    h["vor_population"] = int(pop_by_hosp_vor.get(h["name"], 0))

# ── Generate HTML ──────────────────────────────────────────────────────────────
print("Generating HTML …")

HOSPITALS_JSON = json.dumps(hospitals_js, separators=(",", ":"))
DOTS_FILE      = "comparison_dots.json"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catchment Comparison — Geographic vs Equalised</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }}
  header {{ padding: 14px 24px; background: #1e293b; border-bottom: 1px solid #334155; display: flex; align-items: center; gap: 16px; }}
  header h1 {{ font-size: 1.1rem; font-weight: 600; color: #f1f5f9; }}
  header p  {{ font-size: 0.82rem; color: #94a3b8; }}
  .map-row {{ display: flex; height: calc(100vh - 58px); }}
  .map-col {{ flex: 1; display: flex; flex-direction: column; border-right: 2px solid #334155; }}
  .map-col:last-child {{ border-right: none; }}
  .map-label {{ padding: 8px 16px; background: #1e293b; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; display: flex; align-items: center; gap: 10px; }}
  .map-label .badge {{ padding: 2px 10px; border-radius: 99px; font-size: 0.72rem; }}
  .badge-geo  {{ background: #166534; color: #bbf7d0; }}
  .badge-eq   {{ background: #1e3a8a; color: #bfdbfe; }}
  .map-label .note {{ color: #64748b; font-weight: 400; font-size: 0.72rem; }}
  .leaflet-map {{ flex: 1; }}
  .back-link {{ font-size: 0.75rem; color: #60a5fa; text-decoration: none; margin-left: auto; }}
  .back-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Neonatal Catchment Comparison</h1>
    <p>Left: nearest hospital (geographic Voronoi) &nbsp;·&nbsp; Right: population-equalised (±5%)</p>
  </div>
  <a class="back-link" href="index.html">← Back to lookup</a>
</header>

<div class="map-row">
  <!-- LEFT: Geographic Voronoi -->
  <div class="map-col">
    <div class="map-label">
      <span class="badge badge-geo">Geographic</span>
      Nearest hospital &nbsp;<span class="note">Compact catchments · unequal populations</span>
    </div>
    <div id="map-geo" class="leaflet-map"></div>
  </div>
  <!-- RIGHT: Equalised -->
  <div class="map-col">
    <div class="map-label">
      <span class="badge badge-eq">Equalised</span>
      Population-balanced &nbsp;<span class="note">Equal populations · stretched catchments</span>
    </div>
    <div id="map-eq" class="leaflet-map"></div>
  </div>
</div>

<script>
const HOSPITALS = {HOSPITALS_JSON};
let DOTS = null;

// ── Create both maps ──────────────────────────────────────────────────────────
function makeMap(id) {{
  const m = L.map(id, {{ center: [51.505, -0.09], zoom: 10, zoomControl: false }});
  L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap contributors', maxZoom: 19
  }}).addTo(m);
  L.control.zoom({{ position: 'bottomleft' }}).addTo(m);
  return m;
}}

const mapGeo = makeMap('map-geo');
const mapEq  = makeMap('map-eq');

// Sync pan/zoom between maps
let syncing = false;
function syncMaps(source, target) {{
  source.on('moveend', () => {{
    if (syncing) return;
    syncing = true;
    target.setView(source.getCenter(), source.getZoom(), {{ animate: false }});
    syncing = false;
  }});
}}
syncMaps(mapGeo, mapEq);
syncMaps(mapEq, mapGeo);

// ── Hospital panes ────────────────────────────────────────────────────────────
[mapGeo, mapEq].forEach(m => {{
  m.createPane('hospitalPane');
  m.getPane('hospitalPane').style.zIndex = 650;
}});

// ── Plot dots ─────────────────────────────────────────────────────────────────
function plotDots(dots) {{
  dots.forEach(d => {{
    const hGeo = HOSPITALS[d[2]];
    const hEq  = HOSPITALS[d[3]];
    L.circleMarker([d[0], d[1]], {{
      radius: 2.5, color: hGeo.color, weight: 0,
      fillColor: hGeo.color, fillOpacity: 0.75
    }}).addTo(mapGeo);
    L.circleMarker([d[0], d[1]], {{
      radius: 2.5, color: hEq.color, weight: 0,
      fillColor: hEq.color, fillOpacity: 0.75
    }}).addTo(mapEq);
  }});
}}

fetch('{DOTS_FILE}').then(r => r.json()).then(dots => {{
  DOTS = dots;
  plotDots(dots);
}});

// ── Hospital markers ──────────────────────────────────────────────────────────
HOSPITALS.forEach(h => {{
  if (!h.lat) return;
  const levelLabel = h.level === 3 ? 'NICU (L3)' : h.level === 2 ? 'HDU (L2)' : 'Special Care (L1)';
  const radius = h.level === 3 ? 11 : h.level === 2 ? 9 : 7;

  function makeMarker(map, popupHTML) {{
    L.circleMarker([h.lat, h.lon], {{
      pane: 'hospitalPane', radius: radius + 3, color: 'white', weight: 0,
      fillColor: 'white', fillOpacity: 0.9, interactive: false
    }}).addTo(map);
    L.circleMarker([h.lat, h.lon], {{
      pane: 'hospitalPane', radius, color: '#1A2340', weight: 2,
      fillColor: h.color, fillOpacity: 1
    }}).bindPopup(popupHTML)
      .bindTooltip(h.name, {{ permanent: false, direction: 'top', offset: [0, -12] }})
      .addTo(map);
  }}

  makeMarker(mapGeo,
    '<b>' + h.name + '</b><br>' + levelLabel + '<br>' +
    'Population: <b>' + h.vor_population.toLocaleString() + '</b><br>' +
    'Postcodes: ' + h.vor_count.toLocaleString()
  );
  const devSign = h.eq_pct_dev >= 0 ? '+' : '';
  makeMarker(mapEq,
    '<b>' + h.name + '</b><br>' + levelLabel + '<br>' +
    'Population: <b>' + h.eq_population.toLocaleString() + '</b><br>' +
    'Target: ' + h.eq_target.toLocaleString() + '<br>' +
    'Deviation: <b>' + devSign + h.eq_pct_dev + '%</b><br>' +
    'Postcodes: ' + h.eq_count.toLocaleString()
  );
}});
</script>
</body>
</html>"""

with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Written: {OUTPUT_HTML}  ({len(html)//1024} KB)")
print("Done.")
