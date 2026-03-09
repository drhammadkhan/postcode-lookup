import pandas as pd
import numpy as np
import folium
from folium.plugins import FastMarkerCluster
from shapely.geometry import Point, Polygon
import os

# Thames south-bank polygon (lon, lat).
# Traces the south bank of the Thames from Hampton in the west to
# Greenwich in the east, then closes south to cover all of south London.
# Any North-assigned postcode whose coordinate falls *inside* this polygon
# has a wrong/non-geographic OS grid reference and should not be plotted.
SOUTH_OF_THAMES = Polygon([
    (-0.420, 51.400),
    (-0.380, 51.403),
    (-0.355, 51.405),
    (-0.325, 51.420),
    (-0.295, 51.447),
    (-0.286, 51.466),
    (-0.262, 51.474),
    (-0.240, 51.473),
    (-0.228, 51.471),
    (-0.212, 51.466),
    (-0.196, 51.461),
    (-0.185, 51.459),
    (-0.165, 51.466),
    (-0.152, 51.474),
    (-0.143, 51.481),
    (-0.129, 51.484),
    (-0.121, 51.488),
    (-0.111, 51.494),
    (-0.099, 51.506),
    (-0.083, 51.506),
    (-0.073, 51.504),
    (-0.040, 51.499),
    ( 0.000, 51.494),
    ( 0.040, 51.487),
    ( 0.060, 51.484),
    ( 0.060, 51.380),
    (-0.420, 51.380),
])

# 1. LOAD RESULTS & HOSPITALS
output_files = [f for f in os.listdir('output') if f.endswith('.csv') and f != 'All_Postcodes.csv']
frames = []
for f in output_files:
    df = pd.read_csv(os.path.join('output', f))
    frames.append(df)
results = pd.concat(frames, ignore_index=True)
hospitals = pd.read_csv('hospitals_refined.csv')

# 2. GENERATE DISTINCT COLOURS FOR EACH HOSPITAL, GROUPED BY SECTOR
hospital_names = sorted(results['Closest_Any'].unique())
n = len(hospital_names)

SECTOR_RANGES = {
    'NC':     {'h': (210, 235), 's': (80, 90), 'l': (22, 72)},
    'NE':     {'h': (108, 145), 's': (72, 88), 'l': (20, 68)},
    'NW':     {'h': (268, 308), 's': (68, 85), 'l': (22, 70)},
    'SE':     {'h': (18, 44),   's': (82, 95), 'l': (28, 70)},
    'SW':     {'h': (328, 354), 's': (68, 88), 'l': (32, 74)},
    'Border': {'h': (22, 40),   's': (45, 60), 'l': (22, 62)},
}
SECTOR_ORDER = ['NC', 'NE', 'NW', 'SE', 'SW', 'Border']
SECTOR_LABELS = {
    'NC': 'North Central',
    'NE': 'North East',
    'NW': 'North West',
    'SE': 'South East',
    'SW': 'South West',
    'Border': 'Border',
}
SECTOR_NORMALISATION = {
    'South East': 'SE',
    'South West': 'SW',
}


def normalise_sector(raw_sector):
    if pd.isna(raw_sector):
        return 'Border'
    sector = str(raw_sector).strip()
    sector = SECTOR_NORMALISATION.get(sector, sector)
    return sector if sector in SECTOR_RANGES else 'Border'


def interpolate(start, end, t):
    return round(start + t * (end - start))


def interleaved_order(n_items):
    order = []
    low = 0
    high = n_items - 1
    while low <= high:
        order.append(low)
        low += 1
        if low <= high:
            order.append(high)
            high -= 1
    return order


hospital_sector_map = {
    row['Hospital Name']: normalise_sector(row['Sector'])
    for _, row in hospitals.iterrows()
}
sector_hospitals = {sector: [] for sector in SECTOR_ORDER}
for name in hospital_names:
    sector = hospital_sector_map.get(name, 'Border')
    sector_hospitals[sector].append(name)

for sector in sector_hospitals:
    sector_hospitals[sector].sort()

colour_map = {}
for sector in SECTOR_ORDER:
    names_in_sector = sector_hospitals[sector]
    if not names_in_sector:
        continue
    colour_range = SECTOR_RANGES[sector]
    order = interleaved_order(len(names_in_sector))
    for idx, name in enumerate(names_in_sector):
        t = 0.5 if len(names_in_sector) == 1 else order[idx] / (len(names_in_sector) - 1)
        hue = interpolate(*colour_range['h'], t)
        sat = interpolate(*colour_range['s'], t)
        lit = interpolate(*colour_range['l'], t)
        # Lighten Evelina (St Thomas') and Chelsea & Westminster by increasing lightness by 12%
        if name == "Evelina (St Thomas')" or name == "Chelsea & Westminster":
            lit = min(lit + 12, 100)
        colour_map[name] = f'hsl({hue}, {sat}%, {lit}%)'

# 3. SAMPLE POSTCODES & PLOT AS COLOURED DOTS
SAMPLE_RATE = 5  # plot every 5th postcode (≈65K dots)

# Suppress non-geographic postcodes from map BEFORE sampling.
# Two complementary filters (both require Side == 'North'):
#
#  A) Cluster filter  — coordinate shared by > 50 postcodes in the full dataset.
#     These are large-user/PO Box entries where OS assigns hundreds of postcodes
#     to a single grid reference south of the river.  Fast: no geometry needed.
#
#  B) Thames polygon filter  — coordinate falls inside SOUTH_OF_THAMES polygon.
#     Catches smaller clusters (2–22) and single-coordinate strays that the
#     count threshold misses.  Coordinate counts must be computed on the FULL
#     dataset before sampling, then the polygon test is applied only to the
#     remaining North-assigned rows south of the river (cheap pre-filter on lat).
#
# Genuine south-Fulham / Chelsea / Hammersmith addresses (SW6, W4, SW10, SW3
# near the north bank) are correctly kept because the polygon traces the actual
# meandering south bank — e.g. at lon -0.19 the south bank dips to lat 51.459,
# so SW6 postcodes at lat 51.465–51.481 in Fulham fall OUTSIDE the polygon.

# — Filter A: large non-geographic clusters —
full_coord_counts = results.groupby(['Latitude', 'Longitude'])['Postcode'].transform('count')
cluster_mask = (full_coord_counts > 50) & (results['Side'] == 'North')

# — Filter B: Thames polygon for remaining North-assigned postcodes —
# Pre-filter to candidate rows (North-assigned, south of rough upper bound)
# to avoid running a geometry test on all 326 K rows.
candidate_idx = results.index[
    (~cluster_mask) &
    (results['Side'] == 'North') &
    (results['Latitude'] < 51.510)
]
in_south_polygon = pd.Series(False, index=results.index)
for idx in candidate_idx:
    row = results.loc[idx]
    if SOUTH_OF_THAMES.contains(Point(row['Longitude'], row['Latitude'])):
        in_south_polygon.at[idx] = True

# — Filter C: individual postcode overrides —
# South-assigned postcodes whose OS coordinate is north of the river
# (wrong/non-geographic grid reference, opposite problem to filters A/B).
MAP_SUPPRESS = {
    'SW97RT',   # South-assigned but OS coord at 51.4956,-0.1760 (north of river)
}
manual_mask = results['Postcode'].str.replace(' ', '', regex=False).isin(MAP_SUPPRESS)

non_geographic_mask = cluster_mask | in_south_polygon | manual_mask
n_suppressed = non_geographic_mask.sum()
if n_suppressed:
    print(f"  Suppressing {n_suppressed} non-geographic postcodes from map "
          f"({cluster_mask.sum()} by cluster filter, "
          f"{in_south_polygon.sum()} by Thames polygon, "
          f"{manual_mask.sum()} by manual override)")
results_plot = results[~non_geographic_mask].copy()

sampled = results_plot.iloc[::SAMPLE_RATE].copy()

m = folium.Map(location=[51.5, -0.1], zoom_start=10, tiles=None)
folium.TileLayer('cartodbpositron', name='Base Map').add_to(m)

for name in hospital_names:
    subset = sampled[sampled['Closest_Any'] == name]
    if subset.empty:
        continue

    colour = colour_map[name]
    total = len(results[results['Closest_Any'] == name])

    fg = folium.FeatureGroup(name=name, show=True)

    # Build a single GeoJSON layer per hospital — far more compact than
    # individual CircleMarker objects (88 MB → ~15 MB, tooltips responsive)
    features = [
        {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [row['Longitude'], row['Latitude']]},
            'properties': {'postcode': row['Postcode']}
        }
        for _, row in subset.iterrows()
    ]
    folium.GeoJson(
        {'type': 'FeatureCollection', 'features': features},
        marker=folium.CircleMarker(
            radius=4,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.6,
            weight=0,
        ),
        tooltip=folium.GeoJsonTooltip(fields=['postcode'], labels=False),
    ).add_to(fg)

    fg.add_to(m)

# 4. ADD HOSPITAL MARKERS (on top)
hosp_layer = folium.FeatureGroup(name='Hospitals', show=True)
for _, row in hospitals.iterrows():
    name = row['Hospital Name']
    colour = colour_map.get(name, '#333333')

    folium.CircleMarker(
        location=[row['Latitude'], row['Longitude']],
        radius=8,
        color='black',
        weight=2,
        fill=True,
        fill_color=colour,
        fill_opacity=1.0,
        popup=f"<b>{name}</b><br>Level {row['Level']} | {row['Side']}",
        tooltip=name,
    ).add_to(hosp_layer)
hosp_layer.add_to(m)

# 5. LAYER CONTROL (toggle hospitals on/off)
folium.LayerControl(collapsed=False).add_to(m)

# 6. ADD DESELECT/SELECT ALL BUTTON
toggle_js = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        var ctrl = document.querySelector('.leaflet-control-layers-overlays');
        if (!ctrl) return;
        var btn = document.createElement('div');
        btn.style.cssText = 'padding:6px 0 2px 0;text-align:center;border-top:1px solid #ccc;margin-top:4px;';
        var a = document.createElement('a');
        a.href = '#';
        a.style.cssText = 'cursor:pointer;font-size:12px;color:#2d6a9f;text-decoration:none;font-weight:600;';
        a.textContent = 'Deselect All';
        var allOn = true;
        a.onclick = function(e) {
            e.preventDefault();
            var checks = ctrl.querySelectorAll('input[type=checkbox]');
            allOn = !allOn;
            checks.forEach(function(cb) { if (cb.checked !== allOn) cb.click(); });
            a.textContent = allOn ? 'Deselect All' : 'Select All';
        };
        btn.appendChild(a);
        ctrl.appendChild(btn);
    }, 500);
});
</script>
"""
m.get_root().html.add_child(folium.Element(toggle_js))

# 7. ADD LEGEND
legend_html = """
<div style="
    position: fixed; bottom: 20px; left: 20px; z-index: 9999;
    background: white; padding: 12px 16px; border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25); font-size: 12px;
    max-height: 60vh; overflow-y: auto; line-height: 1.8;
">
<b style="font-size:13px">Neonatal Catchment Areas</b><br>
"""
for sector in SECTOR_ORDER:
    names_in_sector = sector_hospitals[sector]
    if not names_in_sector:
        continue
    legend_html += (
        f'<div style="margin-top:8px;margin-bottom:2px;font-size:10px;'
        f'text-transform:uppercase;letter-spacing:.06em;color:#718096;'
        f'font-weight:700;">{SECTOR_LABELS[sector]}</div>'
    )
    for name in names_in_sector:
        c = colour_map[name]
        count = len(results[results['Closest_Any'] == name])
        legend_html += (
            f'<span style="background:{c}; width:12px; height:12px; '
            f'display:inline-block; border-radius:2px; margin-right:6px;"></span>'
            f'{name} ({count:,})<br>'
        )
legend_html += "</div>"
m.get_root().html.add_child(folium.Element(legend_html))

# 8. SAVE
m.save('neonatal_catchment_map.html')
print(f"Map saved → neonatal_catchment_map.html")
print(f"  {n} hospitals, {len(sampled):,} sampled dots (1/{SAMPLE_RATE} of {len(results):,})")
