"""
Build a compact JSON lookup for the static GitHub Pages site.
Strips lat/lon to 4 decimal places, uses short keys, and outputs
a single JSON file that JS can fetch and search client-side.
Also exports a hospitals JSON.
"""
import pandas as pd
import json
import os

os.makedirs('docs', exist_ok=True)

# 1. Load data
df = pd.read_csv('output/All_Postcodes.csv', dtype={'Postcode': str})
hospitals = pd.read_csv('hospitals_refined.csv')

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

# 3. Save as JSON with hospital name index
output = {'names': all_hosp_names, 'data': records}
with open('docs/postcodes.json', 'w') as f:
    json.dump(output, f, separators=(',', ':'))
size_mb = os.path.getsize('docs/postcodes.json') / (1024 * 1024)
print(f"docs/postcodes.json → {size_mb:.1f} MB ({len(records):,} postcodes)")

# 4. Hospitals JSON
hosp_list = []
for _, row in hospitals.iterrows():
    tags = ''
    if pd.notna(row.get('Specialty Tags', '')):
        tags = str(row['Specialty Tags']).strip()
    hosp_list.append({
        'name': row['Hospital Name'],
        'level': int(row['Level']),
        'side': row['Side'],
        'lat': round(row['Latitude'], 4),
        'lon': round(row['Longitude'], 4),
        'tags': tags,
    })

with open('docs/hospitals.json', 'w') as f:
    json.dump(hosp_list, f, separators=(',', ':'))
print(f"docs/hospitals.json → {len(hosp_list)} hospitals")
