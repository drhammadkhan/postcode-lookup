import pandas as pd
import numpy as np
import folium
from folium.plugins import FastMarkerCluster
import colorsys, os

# 1. LOAD RESULTS & HOSPITALS
output_files = [f for f in os.listdir('output') if f.endswith('.csv')]
frames = []
for f in output_files:
    df = pd.read_csv(os.path.join('output', f))
    frames.append(df)
results = pd.concat(frames, ignore_index=True)
hospitals = pd.read_csv('hospitals_refined.csv')

# 2. GENERATE DISTINCT COLOURS FOR EACH HOSPITAL
hospital_names = sorted(results['Closest_Any'].unique())
n = len(hospital_names)

def generate_colours(n):
    """Generate n visually distinct colours."""
    colours = []
    for i in range(n):
        hue = i / n
        r, g, b = colorsys.hls_to_rgb(hue, 0.45, 0.75)
        colours.append(f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}')
    return colours

colour_list = generate_colours(n)
colour_map = dict(zip(hospital_names, colour_list))

# 3. SAMPLE POSTCODES & PLOT AS COLOURED DOTS
SAMPLE_RATE = 5  # plot every 5th postcode (≈65K dots)
sampled = results.iloc[::SAMPLE_RATE].copy()

m = folium.Map(location=[51.5, -0.1], zoom_start=10, tiles='cartodbpositron')

for name in hospital_names:
    subset = sampled[sampled['Closest_Any'] == name]
    if subset.empty:
        continue

    colour = colour_map[name]
    total = len(results[results['Closest_Any'] == name])

    fg = folium.FeatureGroup(name=name, show=True)

    for _, row in subset.iterrows():
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=2,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.6,
            weight=0,
            tooltip=row['Postcode'],
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

# 6. ADD LEGEND
legend_html = """
<div style="
    position: fixed; bottom: 20px; left: 20px; z-index: 9999;
    background: white; padding: 12px 16px; border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25); font-size: 12px;
    max-height: 60vh; overflow-y: auto; line-height: 1.8;
">
<b style="font-size:13px">Neonatal Catchment Areas</b><br>
"""
for name in hospital_names:
    c = colour_map[name]
    count = len(results[results['Closest_Any'] == name])
    legend_html += (
        f'<span style="background:{c}; width:12px; height:12px; '
        f'display:inline-block; border-radius:2px; margin-right:6px;"></span>'
        f'{name} ({count:,})<br>'
    )
legend_html += "</div>"
m.get_root().html.add_child(folium.Element(legend_html))

# 7. SAVE
m.save('neonatal_catchment_map.html')
print(f"Map saved → neonatal_catchment_map.html")
print(f"  {n} hospitals, {len(sampled):,} sampled dots (1/{SAMPLE_RATE} of {len(results):,})")
