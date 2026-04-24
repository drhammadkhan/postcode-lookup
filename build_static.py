"""
Build a compact JSON lookup for the static GitHub Pages site.
Strips lat/lon to 4 decimal places, uses short keys, and outputs
a single JSON file that JS can fetch and search client-side.
Also exports a hospitals JSON.
"""
import pandas as pd
import json
import os
from shapely.geometry import Point, Polygon

os.makedirs('docs', exist_ok=True)

# 1. Load data
df = pd.read_csv('output/All_Postcodes.csv', dtype={'Postcode': str})
hospitals = pd.read_csv('hospitals_refined.csv')

# Thames south-bank polygon (lon, lat) used by generate_map.py.
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
    (0.000, 51.494),
    (0.040, 51.487),
    (0.060, 51.484),
    (0.060, 51.380),
    (-0.420, 51.380),
])
MAP_SUPPRESS = {'SW97RT'}

# 2. Build compact postcode lookup using hospital name indices
# Deduplicate hospital names into an array, reference by index
all_hosp_names = sorted(set(
    df['Closest_Any'].unique().tolist() +
    df['Closest_L1'].unique().tolist() +
    df['Closest_L2'].unique().tolist() +
    df['Closest_L3'].unique().tolist()
))
name_to_idx = {name: i for i, name in enumerate(all_hosp_names)}

records = {}
for _, row in df.iterrows():
    key = row['Postcode'].replace(' ', '').upper()
    records[key] = [
        row['Postcode'],
        round(row['Latitude'], 4),
        round(row['Longitude'], 4),
        0 if row['Side'] == 'North' else 1,
        name_to_idx[row['Closest_Any']],
        round(row['Distance_Any_km'], 2),
        name_to_idx[row['Closest_L1']],
        round(row['Distance_L1_km'], 2),
        name_to_idx[row['Closest_L2']],
        round(row['Distance_L2_km'], 2),
        name_to_idx[row['Closest_L3']],
        round(row['Distance_L3_km'], 2),
    ]

# 3. Build pre-filtered catchment points for static map (matches generate_map.py)
sample_rate = 5

full_coord_counts = df.groupby(['Latitude', 'Longitude'])['Postcode'].transform('count')
cluster_mask = (full_coord_counts > 50) & (df['Side'] == 'North')

candidate_idx = df.index[
    (~cluster_mask) &
    (df['Side'] == 'North') &
    (df['Latitude'] < 51.510)
]
in_south_polygon = pd.Series(False, index=df.index)
for idx in candidate_idx:
    row = df.loc[idx]
    if SOUTH_OF_THAMES.contains(Point(row['Longitude'], row['Latitude'])):
        in_south_polygon.at[idx] = True

manual_mask = df['Postcode'].str.replace(' ', '', regex=False).isin(MAP_SUPPRESS)
non_geographic_mask = cluster_mask | in_south_polygon | manual_mask

results_plot = df[~non_geographic_mask]
sampled_plot = results_plot.iloc[::sample_rate]

catchment_points = [
    [
        row.Postcode,
        float(row.Latitude),
        float(row.Longitude),
        name_to_idx[row.Closest_Any],
    ]
    for row in sampled_plot.itertuples(index=False)
]

counts_any = df['Closest_Any'].value_counts()
counts_any_indexed = [int(counts_any.get(name, 0)) for name in all_hosp_names]

# 3. Save as JSON with hospital name index
output = {
    'names': all_hosp_names,
    'data': records,
    'catchment': {
        'sample_rate': sample_rate,
        'suppressed_total': int(non_geographic_mask.sum()),
        'suppressed_breakdown': {
            'cluster': int(cluster_mask.sum()),
            'polygon': int(in_south_polygon.sum()),
            'manual': int(manual_mask.sum()),
        },
        'points': catchment_points,
        'counts_any': counts_any_indexed,
    }
}
with open('docs/postcodes.json', 'w') as f:
    json.dump(output, f, separators=(',', ':'))
size_mb = os.path.getsize('docs/postcodes.json') / (1024 * 1024)
print(f"docs/postcodes.json → {size_mb:.1f} MB ({len(records):,} postcodes)")
print(
    "  Catchment points: "
    f"{len(catchment_points):,} (1/{sample_rate} of {len(results_plot):,} after suppression; "
    f"suppressed {int(non_geographic_mask.sum()):,})"
)

# 4. Hospitals JSON
hosp_list = []
for _, row in hospitals.iterrows():
    tags = ''
    if pd.notna(row.get('Specialty Tags', '')):
        tags = str(row['Specialty Tags']).strip()
    hosp_list.append({
        'name': row['Hospital Name'],
        'level': int(row['Level']),
        'sector': {'South East': 'SE', 'South West': 'SW'}.get(str(row['Sector']).strip(), str(row['Sector']).strip()) if pd.notna(row.get('Sector', '')) else '',
        'side': row['Side'],
        'lat': round(row['Latitude'], 4),
        'lon': round(row['Longitude'], 4),
        'tags': tags,
    })

with open('docs/hospitals.json', 'w') as f:
    json.dump(hosp_list, f, separators=(',', ':'))
print(f"docs/hospitals.json → {len(hosp_list)} hospitals")
