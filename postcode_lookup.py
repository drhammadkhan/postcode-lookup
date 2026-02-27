import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

# 1. LOAD DATA
hospitals = pd.read_csv('hospitals_refined.csv')
postcodes = pd.read_csv('postcodes_master.csv')

# 2. HAVERSINE DISTANCE (vectorised, returns km)
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance between arrays of coordinates in km."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))

# 3. FUNCTION TO DETERMINE SIDE OF RIVER
def get_side(pc):
    outcode = pc.split(' ')[0].upper()
    north_prefixes = {'N', 'NW', 'E', 'EN', 'HA', 'IG', 'RM', 'UB', 'WD', 'WC', 'EC', 'W'}
    # SW districts that sit north of the Thames
    north_sw_districts = {'1', '3', '5', '6', '7', '10'}

    # Extract only LEADING letters as the area code (WC2R → WC, EC1A → EC, SW1A → SW)
    prefix = ''
    for c in outcode:
        if c.isalpha():
            prefix += c
        else:
            break

    if prefix == 'SW':
        # Extract just the numeric district (e.g. SW1A → '1', SW10 → '10')
        district_num = ''.join(c for c in outcode[len(prefix):] if c.isdigit())
        return 'North' if district_num in north_sw_districts else 'South'

    return 'North' if prefix in north_prefixes else 'South'

# 4. VECTORISED SPATIAL SEARCH
def find_nearest(pc_group, hosp_subset):
    """Find nearest hospital for a batch of postcodes using a single KD-tree."""
    n = len(pc_group)
    if hosp_subset.empty:
        return (pd.Series(["None Found"] * n, index=pc_group.index),
                pd.Series([0.0] * n, index=pc_group.index))

    # Scale longitude by cos(lat) so Euclidean ≈ true distance at London's latitude
    cos_lat = np.cos(np.radians(51.5))
    scale = np.array([1.0, cos_lat])

    hosp_coords = hosp_subset[['Latitude', 'Longitude']].values * scale
    pc_coords   = pc_group[['Latitude', 'Longitude']].values * scale

    tree = cKDTree(hosp_coords)
    _, indices = tree.query(pc_coords)

    matched = hosp_subset.iloc[indices]
    names = pd.Series(matched['Hospital Name'].values, index=pc_group.index)

    # Accurate Haversine distances on the original (unscaled) coordinates
    dists = haversine(
        pc_group['Latitude'].values, pc_group['Longitude'].values,
        matched['Latitude'].values, matched['Longitude'].values
    )
    dists = pd.Series(np.round(dists, 2), index=pc_group.index)

    return names, dists

# 5. EXECUTION
postcodes['Side'] = postcodes['Postcode'].apply(get_side)
results = postcodes[['Postcode', 'Side']].copy()

for side in ['North', 'South']:
    pc_group = postcodes[postcodes['Side'] == side]
    hosp_side = hospitals[hospitals['Side'].isin([side, 'Both'])]

    for label, level in [('Any', None), ('L1', 1), ('L2', 2), ('L3', 3)]:
        hosp_subset = hosp_side if level is None else hosp_side[hosp_side['Level'] == level]
        names, dists = find_nearest(pc_group, hosp_subset.reset_index(drop=True))
        results.loc[pc_group.index, f'Closest_{label}'] = (
            names + ' (' + dists.astype(str) + 'km)'
        )

results.to_csv('Neonatal_Lookup_Final.csv', index=False)
print(f"Done! {len(results)} postcodes processed.")
