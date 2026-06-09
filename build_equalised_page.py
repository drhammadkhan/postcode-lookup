#!/usr/bin/env python3
"""
build_equalised_page.py

Generates docs/equalised_catchment.html — a static page visualising the
equalised catchment areas produced by equalise_catchments.py.

The page contains:
  • A full-width Leaflet map with one coloured dot per postcode (1-in-5 sample),
    coloured by the hospital it was assigned to, plus a toggleable layer per
    hospital with a matching hospital marker.
  • A bar chart (Chart.js) comparing assigned populations across hospitals.
  • A summary table with postcode count, population, and % deviation from target.

Run:
    python3 build_equalised_page.py
Output:
    docs/equalised_catchment.html
"""

import json
import re
import pandas as pd
import numpy as np
from shapely.geometry import Polygon, Point

from hospital_profiles import load_hospitals_for_profile

# ── Inputs ────────────────────────────────────────────────────────────────────

EQUALISED_CSV  = "output/All_Postcodes_Equalised.csv"
SUMMARY_CSV    = "output/Equalised_Summary.csv"
HOSPITALS_CSV  = "hospitals_refined.csv"
OUTPUT_HTML    = "docs/equalised_catchment.html"
OUTPUT_DOTS    = "docs/equalised_dots.json"
SAMPLE_RATE    = 5   # keep every Nth postcode for the map

# ── Colour palette (mirrors generate_map.py) ──────────────────────────────────

SECTOR_RANGES = {
    'NC':     {'h': (210, 235), 's': (80, 90),  'l': (22, 72)},
    'NE':     {'h': (108, 145), 's': (72, 88),  'l': (20, 68)},
    'NW':     {'h': (268, 308), 's': (68, 85),  'l': (22, 70)},
    'SE':     {'h': (18,  44),  's': (82, 95),  'l': (28, 70)},
    'SW':     {'h': (328, 354), 's': (68, 88),  'l': (32, 74)},
    'Border': {'h': (22,  40),  's': (45, 60),  'l': (22, 62)},
}
SECTOR_ORDER = ['NC', 'NE', 'NW', 'SE', 'SW', 'Border']
SECTOR_NORMALISATION = {'South East': 'SE', 'South West': 'SW'}

def normalise_sector(raw):
    s = str(raw).strip() if pd.notna(raw) else 'Border'
    return SECTOR_NORMALISATION.get(s, s) if s in {*SECTOR_NORMALISATION, *SECTOR_RANGES} else 'Border'

def interleaved_order(n):
    order, lo, hi = [], 0, n - 1
    while lo <= hi:
        order.append(lo); lo += 1
        if lo <= hi: order.append(hi); hi -= 1
    return order

def hsl_str(h, s, l):
    return f'hsl({h},{s}%,{l}%)'

# ── Load data ─────────────────────────────────────────────────────────────────

print("Loading data …")
eq  = pd.read_csv(EQUALISED_CSV)
summ = pd.read_csv(SUMMARY_CSV)
hosp_df = load_hospitals_for_profile(HOSPITALS_CSV, profile="analysis")
hosp_df["Hospital Name"] = hosp_df["Hospital Name"].str.strip()

# One row per hospital name (take first occurrence — enough for lat/lon/sector/level)
hosp_info = (
    hosp_df.groupby("Hospital Name", as_index=False)
    .first()
    .set_index("Hospital Name")
)

# ── Build colour map ──────────────────────────────────────────────────────────

all_hospitals = sorted(eq["New_Hospital"].dropna().unique())

sector_hospitals = {s: [] for s in SECTOR_ORDER}
for name in all_hospitals:
    sector = normalise_sector(hosp_info.loc[name, "Sector"] if name in hosp_info.index else "Border")
    sector_hospitals[sector].append(name)
for s in sector_hospitals:
    sector_hospitals[s].sort()

colour_map = {}
for sector in SECTOR_ORDER:
    names = sector_hospitals[sector]
    if not names:
        continue
    r = SECTOR_RANGES[sector]
    order = interleaved_order(len(names))
    for idx, name in enumerate(names):
        t = 0.5 if len(names) == 1 else order[idx] / (len(names) - 1)
        h = round(r['h'][0] + t * (r['h'][1] - r['h'][0]))
        s = round(r['s'][0] + t * (r['s'][1] - r['s'][0]))
        l = round(r['l'][0] + t * (r['l'][1] - r['l'][0]))
        if name in ("Evelina (St Thomas')", "Chelsea & Westminster"):
            l = min(l + 12, 100)
        colour_map[name] = hsl_str(h, s, l)

# ── Non-geographic suppression (mirrors generate_map.py) ─────────────────────

SOUTH_OF_THAMES = Polygon([
    (-0.420, 51.400), (-0.385, 51.417), (-0.340, 51.437),
    (-0.308, 51.450), (-0.280, 51.459), (-0.250, 51.462),
    (-0.220, 51.464), (-0.190, 51.459), (-0.165, 51.462),
    (-0.140, 51.470), (-0.115, 51.481), (-0.090, 51.482),
    (-0.065, 51.494), (-0.040, 51.497), (-0.010, 51.501),
    ( 0.010, 51.503), ( 0.025, 51.506), ( 0.040, 51.502),
    ( 0.055, 51.497), ( 0.060, 51.484),
    ( 0.060, 51.380), (-0.420, 51.380),
])
MAP_SUPPRESS = {'SW97RT'}

coord_counts = eq.groupby(['Latitude', 'Longitude'])['Postcode'].transform('count')
cluster_mask = (coord_counts > 50) & (eq['Side'] == 'North')

north_cand = eq[~cluster_mask & (eq['Side'] == 'North') & (eq['Latitude'] < 51.52)].copy()
poly_suppress = set()
for _, row in north_cand.iterrows():
    if SOUTH_OF_THAMES.contains(Point(row['Longitude'], row['Latitude'])):
        poly_suppress.add(row['Postcode'].replace(' ', ''))

manual_suppress = MAP_SUPPRESS
suppress_mask = (
    cluster_mask |
    eq['Postcode'].str.replace(' ', '', regex=False).isin(poly_suppress | manual_suppress)
)
clean = eq[~suppress_mask].reset_index(drop=True)

# ── Build hospital index & summary ───────────────────────────────────────────

print("Building hospital metadata …")

hosp_names   = all_hospitals   # consistent ordering
hosp_idx_map = {name: i for i, name in enumerate(hosp_names)}

# Merge summary with hosp_info
summ_indexed = summ.set_index("Hospital")

hospitals_js = []
for name in hosp_names:
    colour = colour_map.get(name, '#888')
    info   = hosp_info.loc[name] if name in hosp_info.index else None
    s_row  = summ_indexed.loc[name] if name in summ_indexed.index else None
    hospitals_js.append({
        "name":          name,
        "lat":           round(float(info["Latitude"]),  4) if info is not None else None,
        "lon":           round(float(info["Longitude"]), 4) if info is not None else None,
        "level":         int(info["Level"])   if info is not None else None,
        "sector":        normalise_sector(info["Sector"]) if info is not None else "Border",
        "side":          str(info["Side"])    if info is not None else "Both",
        "color":         colour,
        "population":    int(s_row["Assigned_Weight"].sum() if hasattr(s_row["Assigned_Weight"], "sum") else s_row["Assigned_Weight"]) if s_row is not None else 0,
        "target":        int(float(s_row["Target"].iloc[0] if hasattr(s_row["Target"], "iloc") else s_row["Target"])) if s_row is not None else 0,
        "pct_dev":       round(float(s_row["Pct_vs_Target"].iloc[0] if hasattr(s_row["Pct_vs_Target"], "iloc") else s_row["Pct_vs_Target"]), 1) if s_row is not None else 0,
        "postcode_count":int(s_row["Postcode_Count"].sum() if hasattr(s_row["Postcode_Count"], "sum") else s_row["Postcode_Count"]) if s_row is not None else 0,
    })

# ── Sample postcodes for the map ─────────────────────────────────────────────

print("Sampling postcodes …")
sampled = clean.iloc[::SAMPLE_RATE].copy()
sampled = sampled[sampled["New_Hospital"].notna()]

# Compact dot array: [[lat4dp, lon4dp, hosp_idx], ...]
dots = [
    [round(r.Latitude, 4), round(r.Longitude, 4), hosp_idx_map[r.New_Hospital]]
    for r in sampled.itertuples()
    if r.New_Hospital in hosp_idx_map
]
print(f"  {len(dots):,} map dots ({len(sampled):,} sampled postcodes)")

# ── Serialize to JSON ─────────────────────────────────────────────────────────

hospitals_json = json.dumps(hospitals_js, separators=(',', ':'))

# Write dots to a separate file to keep the HTML small
with open(OUTPUT_DOTS, 'w') as f:
    json.dump(dots, f, separators=(',', ':'))
print(f"  Dots JSON → {OUTPUT_DOTS}  ({len(json.dumps(dots, separators=(',',':')).encode())/1024:.0f} KB)")

# ── Stats for header cards ────────────────────────────────────────────────────

total_pop    = sum(h["population"] for h in hospitals_js)
n_hospitals  = len(hospitals_js)
max_dev      = max(abs(h["pct_dev"]) for h in hospitals_js)
mean_dev     = round(sum(abs(h["pct_dev"]) for h in hospitals_js) / n_hospitals, 1)

# ── Generate HTML ─────────────────────────────────────────────────────────────

print("Generating HTML …")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Equalised Catchments — HO.ME Neonatal</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
*, *::before, *::after {{ margin:0; padding:0; box-sizing:border-box; }}
:root {{
  --blue:#1855A3; --blue-dark:#0F3D7A; --blue-light:#EBF3FF; --blue-mid:#2D74CC;
  --bg:#F4F7FC; --surface:#FFFFFF; --border:#E2E8F2;
  --text:#1A2340; --text-mid:#4A5577; --text-soft:#8A95B0;
  --green:#16A34A; --green-light:#F0FDF4;
  --amber:#D97706; --amber-light:#FFFBEB;
  --red:#DC2626; --red-light:#FFF5F5;
  --radius:14px; --shadow:0 2px 16px rgba(24,85,163,0.08);
  --shadow-lg:0 8px 32px rgba(24,85,163,0.14);
}}
body {{ font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
        background:var(--bg); color:var(--text); min-height:100vh; display:flex; flex-direction:column; }}
header {{ background:var(--surface); border-bottom:1px solid var(--border); }}
.header-inner {{ max-width:1200px; margin:0 auto; padding:1.25rem 1.5rem;
                 display:flex; align-items:center; justify-content:space-between; gap:1.5rem; }}
.brand-home {{ font-size:2rem; font-weight:900; color:var(--blue); letter-spacing:-0.04em; }}
.brand-sep  {{ font-size:1.5rem; font-weight:300; color:var(--text-soft); margin:0 0.4rem; }}
.brand-full {{ font-size:1.25rem; font-weight:700; color:var(--blue); letter-spacing:-0.02em; }}
.brand-tagline {{ font-size:0.875rem; color:var(--text-mid); margin-top:0.1rem; }}
.header-nav a {{ font-size:0.85rem; font-weight:600; color:var(--text-mid);
                 text-decoration:none; padding:0.4rem 0.75rem; border-radius:8px;
                 transition:all 0.15s; }}
.header-nav a:hover {{ color:var(--blue); background:var(--blue-light); }}
main {{ flex:1; max-width:1200px; margin:0 auto; padding:1.75rem 1.5rem; width:100%; }}
h1 {{ font-size:1.5rem; font-weight:800; color:var(--text); letter-spacing:-0.03em; margin-bottom:0.35rem; }}
.subtitle {{ font-size:0.9rem; color:var(--text-mid); margin-bottom:1.5rem; }}

/* Stat cards */
.stat-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:0.85rem; margin-bottom:1.5rem; }}
@media(max-width:700px){{ .stat-grid {{ grid-template-columns:repeat(2,1fr); }} }}
.stat-card {{ background:var(--surface); border-radius:var(--radius); box-shadow:var(--shadow);
              padding:1.1rem 1.25rem; }}
.stat-label {{ font-size:0.72rem; font-weight:600; color:var(--text-soft);
               text-transform:uppercase; letter-spacing:0.07em; margin-bottom:0.4rem; }}
.stat-value {{ font-size:1.7rem; font-weight:800; color:var(--blue); letter-spacing:-0.03em; line-height:1; }}
.stat-sub   {{ font-size:0.78rem; color:var(--text-mid); margin-top:0.25rem; }}

/* Tabs */
.tabs {{ display:flex; gap:4px; margin-bottom:1.25rem; background:var(--surface);
         border-radius:var(--radius); padding:5px; box-shadow:var(--shadow); width:fit-content; }}
.tab {{ padding:0.6rem 1.25rem; font-size:0.88rem; font-weight:600; cursor:pointer;
        border:none; background:transparent; color:var(--text-mid); border-radius:10px;
        transition:all 0.18s; font-family:inherit; }}
.tab:hover {{ color:var(--blue); background:var(--blue-light); }}
.tab.active {{ background:var(--blue); color:#fff; box-shadow:0 2px 8px rgba(24,85,163,0.3); }}
.tab-content {{ display:none; }}
.tab-content.active {{ display:block; }}

/* Map */
#map {{ width:100%; height:620px; border-radius:var(--radius); box-shadow:var(--shadow-lg);
        margin-bottom:0.75rem; }}
.map-note {{ font-size:0.78rem; color:var(--text-soft); margin-bottom:1.5rem; }}

/* Chart */
.chart-card {{ background:var(--surface); border-radius:var(--radius);
               box-shadow:var(--shadow); padding:1.5rem 1.75rem; margin-bottom:1.25rem; }}
.chart-title {{ font-size:1rem; font-weight:700; color:var(--text); margin-bottom:1.1rem; }}
.chart-wrap  {{ position:relative; height:520px; }}

/* Table */
.table-card {{ background:var(--surface); border-radius:var(--radius);
               box-shadow:var(--shadow); overflow:hidden; margin-bottom:1.25rem; }}
.table-header {{ padding:1.1rem 1.5rem; border-bottom:1px solid var(--border);
                 font-size:0.85rem; font-weight:700; color:var(--text); display:flex;
                 align-items:center; justify-content:space-between; }}
table {{ width:100%; border-collapse:collapse; font-size:0.875rem; }}
th {{ padding:0.7rem 1rem; background:var(--bg); font-size:0.72rem; font-weight:700;
      text-transform:uppercase; letter-spacing:0.06em; color:var(--text-soft);
      text-align:left; border-bottom:1px solid var(--border); white-space:nowrap; }}
th.r, td.r {{ text-align:right; }}
td {{ padding:0.65rem 1rem; border-bottom:1px solid var(--border); color:var(--text); }}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:var(--blue-light); }}
.swatch {{ display:inline-block; width:12px; height:12px; border-radius:3px;
           margin-right:6px; vertical-align:middle; flex-shrink:0; }}
.dev-pos {{ color:var(--amber); font-weight:600; }}
.dev-neg {{ color:var(--blue);  font-weight:600; }}
.dev-ok  {{ color:var(--green); font-weight:600; }}
.pill-n  {{ background:var(--blue-light); color:var(--blue); font-size:0.7rem;
            font-weight:700; padding:0.15rem 0.55rem; border-radius:99px; }}
.pill-s  {{ background:#FFFBE6; color:#92400E; font-size:0.7rem;
            font-weight:700; padding:0.15rem 0.55rem; border-radius:99px; }}
.legend-toggle {{ background:var(--blue); color:#fff; border:none; padding:0.5rem 1rem;
                  border-radius:8px; font-size:0.8rem; font-weight:600; cursor:pointer;
                  font-family:inherit; }}
.legend-toggle:hover {{ background:var(--blue-dark); }}
.method-box {{ background:var(--blue-light); border:1px solid #B8D4F5;
               border-radius:var(--radius); padding:1.1rem 1.5rem; margin-bottom:1.5rem;
               font-size:0.85rem; color:var(--text-mid); line-height:1.6; }}
.method-box strong {{ color:var(--blue); }}
footer {{ background:var(--surface); border-top:1px solid var(--border);
          padding:1.25rem 1.5rem; text-align:center; font-size:0.82rem; color:var(--text-soft); }}
footer a {{ color:var(--blue); text-decoration:none; }}
footer a:hover {{ text-decoration:underline; }}
</style>
</head>
<body>

<header>
  <div class="header-inner">
    <div>
      <div style="display:flex;align-items:baseline;gap:0.4rem;">
        <span class="brand-home">HO.ME</span>
        <span class="brand-sep">—</span>
        <span class="brand-full">Equalised Catchments</span>
      </div>
      <div class="brand-tagline">Population-balanced neonatal unit boundaries · London</div>
    </div>
    <nav class="header-nav" style="display:flex;gap:0.25rem;flex-wrap:wrap;">
      <a href="index.html">🔍 Postcode Lookup</a>
      <a href="population.html">📊 Catchment Data</a>
      <a href="extra_maps.html">🗺️ Extra Maps</a>
    </nav>
  </div>
</header>

<main>
  <h1>Population-Equalised Catchment Areas</h1>
  <p class="subtitle">Hypothetical catchment boundaries if each hospital served an equal residential population, subject to the North/South Thames divide and geographic contiguity.</p>

  <div class="method-box">
    <strong>Methodology:</strong> Starting from the nearest-hospital (Voronoi) assignment, postcodes are iteratively transferred between neighbouring hospital territories using a priority-heap algorithm. At each step the most over-populated hospital offers a boundary postcode to its most under-populated neighbour. Multiple passes are run until no further improving transfers exist. The North/South Thames boundary is enforced by solving each side independently. Hospitals that are geographically absent from a side (e.g. Wexham Park on the South side) are excluded.
  </div>

  <!-- Stat cards -->
  <div class="stat-grid">
    <div class="stat-card">
      <div class="stat-label">Total Population</div>
      <div class="stat-value">{total_pop:,}</div>
      <div class="stat-sub">ONS Census 2021 residents</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Hospitals</div>
      <div class="stat-value">{n_hospitals}</div>
      <div class="stat-sub">across North &amp; South sides</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Max Deviation</div>
      <div class="stat-value">±{max_dev:.1f}%</div>
      <div class="stat-sub">from per-side target</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Mean Absolute Dev.</div>
      <div class="stat-value">{mean_dev:.1f}%</div>
      <div class="stat-sub">average across hospitals</div>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab active" onclick="switchTab('map')">🗺️ Map</button>
    <button class="tab" onclick="switchTab('chart')">📊 Chart</button>
    <button class="tab" onclick="switchTab('table')">📋 Table</button>
  </div>

  <!-- Map tab -->
  <div id="tab-map" class="tab-content active">
    <div id="map"></div>
    <p class="map-note">Each dot is one postcode (1-in-{SAMPLE_RATE} sample, ~{len(dots):,} shown). Colour = equalised hospital assignment. Click a hospital marker for details. Use the layer control (top-right) to toggle hospitals or deselect all.</p>
  </div>

  <!-- Chart tab -->
  <div id="tab-chart" class="tab-content">
    <div class="chart-card">
      <div class="chart-title">Assigned Population per Hospital</div>
      <div class="chart-wrap"><canvas id="barChart"></canvas></div>
    </div>
  </div>

  <!-- Table tab -->
  <div id="tab-table" class="tab-content">
    <div class="table-card">
      <div class="table-header">
        <span>All hospitals — sorted by assigned population</span>
      </div>
      <div style="overflow-x:auto;">
        <table id="summaryTable">
          <thead>
            <tr>
              <th>Hospital</th>
              <th>Side</th>
              <th>Level</th>
              <th class="r">Postcodes</th>
              <th class="r">Population</th>
              <th class="r">Target</th>
              <th class="r">Δ vs Target</th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</main>

<footer>
  <p>
    <a href="index.html">← Postcode Lookup</a>
    &nbsp;·&nbsp;
    <a href="population.html">Catchment Data</a>
    &nbsp;·&nbsp;
    Data: ONS Census 2021 · Algorithm: Capacitated Region Growing
  </p>
</footer>

<script>
const HOSPITALS = {hospitals_json};
let   DOTS      = null;

// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach((t,i) => {{
    const names = ['map','chart','table'];
    t.classList.toggle('active', names[i] === name);
  }});
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'map' && !mapInitialised) initMap();
  if (name === 'chart' && !chartInitialised) initChart();
  if (name === 'table' && !tableInitialised) initTable();
}}

// ── Map ────────────────────────────────────────────────────────────────────
let mapInitialised = false;

function initMap() {{
  mapInitialised = true;
  const map = L.map('map').setView([51.50, -0.12], 10);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '© OpenStreetMap contributors © CARTO', maxZoom: 19
  }}).addTo(map);

  // Group layers by hospital
  const layers = {{}};
  const overlays = {{}};

  HOSPITALS.forEach((h, idx) => {{
    layers[idx] = L.layerGroup();
  }});

  const plotDots = dots => {{
    dots.forEach(d => {{
      const h = HOSPITALS[d[2]];
      L.circleMarker([d[0], d[1]], {{
        radius: 2.5, color: h.color, weight: 0,
        fillColor: h.color, fillOpacity: 0.75
      }}).addTo(layers[d[2]]);
    }});
    Object.values(layers).forEach(lg => lg.addTo(map));
  }};

  if (DOTS) {{
    plotDots(DOTS);
  }} else {{
    fetch('equalised_dots.json').then(r => r.json()).then(dots => {{
      DOTS = dots;
      plotDots(DOTS);
    }});
  }}

  // Hospital markers — separate pane so they always render above postcode dots
  map.createPane('hospitalPane');
  map.getPane('hospitalPane').style.zIndex = 650;

  const hospitalLayer = L.layerGroup().addTo(map);

  HOSPITALS.forEach((h, idx) => {{
    if (!h.lat) return;
    const levelLabel = h.level === 3 ? 'NICU (L3)' : h.level === 2 ? 'HDU (L2)' : 'Special Care (L1)';
    const devSign = h.pct_dev >= 0 ? '+' : '';
    const radius = h.level === 3 ? 11 : h.level === 2 ? 9 : 7;
    // Outer ring (white halo)
    L.circleMarker([h.lat, h.lon], {{
      pane: 'hospitalPane',
      radius: radius + 3, color: 'white', weight: 0,
      fillColor: 'white', fillOpacity: 0.9, interactive: false
    }}).addTo(hospitalLayer);
    // Coloured fill
    L.circleMarker([h.lat, h.lon], {{
      pane: 'hospitalPane',
      radius: radius, color: '#1A2340', weight: 2,
      fillColor: h.color, fillOpacity: 1
    }}).bindPopup(
      '<b>' + h.name + '</b><br>' +
      levelLabel + ' · ' + h.side + '<br>' +
      'Population: <b>' + h.population.toLocaleString() + '</b><br>' +
      'Target: ' + h.target.toLocaleString() + '<br>' +
      'Deviation: <b>' + devSign + h.pct_dev + '%</b><br>' +
      'Postcodes: ' + h.postcode_count.toLocaleString()
    ).addTo(hospitalLayer);
    // Name label (tooltip)
    L.circleMarker([h.lat, h.lon], {{
      pane: 'hospitalPane', radius: 1, opacity: 0, fillOpacity: 0
    }}).bindTooltip(h.name, {{ permanent: false, direction: 'top', offset: [0, -12] }})
      .addTo(hospitalLayer);
    overlays[h.name] = layers[idx];
  }});

  const ctrl = L.control.layers(null, overlays, {{ collapsed: true, position: 'topright' }}).addTo(map);

  // Deselect All / Select All button
  const btn = L.control({{ position: 'bottomright' }});
  btn.onAdd = () => {{
    const div = L.DomUtil.create('div');
    div.innerHTML = '<button class="legend-toggle" id="toggleAll">Deselect All</button>';
    L.DomEvent.disableClickPropagation(div);
    let allOn = true;
    div.querySelector('#toggleAll').addEventListener('click', () => {{
      allOn = !allOn;
      Object.values(layers).forEach(lg => allOn ? lg.addTo(map) : map.removeLayer(lg));
      div.querySelector('#toggleAll').textContent = allOn ? 'Deselect All' : 'Select All';
    }});
    return div;
  }};
  btn.addTo(map);
}}

// Auto-init map on first load
initMap();

// ── Chart ──────────────────────────────────────────────────────────────────
let chartInitialised = false;

function initChart() {{
  chartInitialised = true;
  const sorted = [...HOSPITALS].sort((a, b) => b.population - a.population);
  const target = sorted[0]?.target || 0;

  new Chart(document.getElementById('barChart'), {{
    type: 'bar',
    data: {{
      labels: sorted.map(h => h.name),
      datasets: [
        {{
          label: 'Assigned Population',
          data: sorted.map(h => h.population),
          backgroundColor: sorted.map(h => h.color),
          borderColor: sorted.map(h => h.color),
          borderWidth: 0,
          borderRadius: 4,
        }},
        {{
          label: 'Target',
          data: sorted.map(() => target),
          type: 'line',
          borderColor: '#DC2626',
          borderWidth: 2,
          borderDash: [6, 4],
          pointRadius: 0,
          fill: false,
          tension: 0,
        }}
      ]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: true, position: 'top' }},
        tooltip: {{
          callbacks: {{
            label: ctx => {{
              const h = sorted[ctx.dataIndex];
              if (ctx.datasetIndex === 1) return ' Target: ' + target.toLocaleString();
              const sign = h.pct_dev >= 0 ? '+' : '';
              return ' ' + h.population.toLocaleString() + '  (' + sign + h.pct_dev + '% vs target)';
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          grid: {{ color: 'rgba(0,0,0,0.05)' }},
          ticks: {{ callback: v => (v/1000).toFixed(0) + 'k', font: {{ size: 11 }} }}
        }},
        y: {{ ticks: {{ font: {{ size: 11 }} }} }}
      }}
    }}
  }});
}}

// ── Table ──────────────────────────────────────────────────────────────────
let tableInitialised = false;

function initTable() {{
  tableInitialised = true;
  const sorted = [...HOSPITALS].sort((a, b) => b.population - a.population);
  const tbody = document.getElementById('tableBody');
  sorted.forEach(h => {{
    const sign  = h.pct_dev >= 0 ? '+' : '';
    const cls   = Math.abs(h.pct_dev) < 2 ? 'dev-ok' : h.pct_dev > 0 ? 'dev-pos' : 'dev-neg';
    const pill  = h.side === 'North'
      ? '<span class="pill-n">North</span>'
      : h.side === 'South'
        ? '<span class="pill-s">South</span>'
        : '<span class="pill-n" style="background:#F0FDF4;color:#16A34A;">Both</span>';
    const lvl   = h.level === 3 ? 'L3 NICU' : h.level === 2 ? 'L2 HDU' : 'L1 SC';
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td><span class="swatch" style="background:' + h.color + '"></span>' + h.name + '</td>' +
      '<td>' + pill + '</td>' +
      '<td>' + lvl + '</td>' +
      '<td class="r">' + h.postcode_count.toLocaleString() + '</td>' +
      '<td class="r"><b>' + h.population.toLocaleString() + '</b></td>' +
      '<td class="r">' + h.target.toLocaleString() + '</td>' +
      '<td class="r ' + cls + '">' + sign + h.pct_dev + '%</td>';
    tbody.appendChild(tr);
  }});
}}
</script>
</body>
</html>"""

with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = len(html.encode()) / 1024
print(f"Written: {OUTPUT_HTML}  ({size_kb:.0f} KB)")
print("Done.")
