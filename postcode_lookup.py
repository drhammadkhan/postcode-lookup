import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import argparse
import os
import re

from hospital_profiles import load_hospitals_for_profile


def parse_args():
    parser = argparse.ArgumentParser(description="Generate postcode-to-hospital nearest lookup tables.")
    parser.add_argument(
        "--profile",
        choices=["lookup", "analysis"],
        default="lookup",
        help="Hospital profile filter to use.",
    )
    parser.add_argument(
        "--hospitals-csv",
        default="hospitals_refined.csv",
        help="Path to hospitals reference CSV.",
    )
    parser.add_argument(
        "--postcodes-csv",
        default="postcodes_master.csv",
        help="Path to master postcodes CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (defaults to output/<profile>).",
    )
    return parser.parse_args()

# 2. HAVERSINE DISTANCE (vectorised, returns km)
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance between arrays of coordinates in km."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))

SOUTH_EXCEPTIONS = {
    'SW1W9FJ', 'SW1P9UP', 'SW1Y6YQ', 'SW1Y5WT',
    'SW1Y4ZB', 'SW1Y6WZ', 'SW1Y5ZP', 'SW1X9UQ', 'SW1X8AX', 'SW1Y5WD', 'SW65DB', 'SW39GA', 'SW39EA', 'SW39BW',
    'SW39DU', 'SW39EG', 'SW39GG', 'SW1Y5ZG', 'SW1X9ZU', 'SW39FX', 'SW39DX', 'SW39FJ', 'SW36XP',
    'SW1W9AT', 'SW1X7WE', 'SW1X7ZJ', 'SW1P9RZ', 'SW1X6WL', 'SW1Y4ZA', 'SW39DN', 'SW39EF', 'SW39GF'
}

# 3. FUNCTION TO DETERMINE SIDE OF RIVER
def get_side(pc):
    pc = pc.strip().upper()
    # Specific postcodes that are exceptions — treated as South despite SW1 prefix
    if pc.replace(' ', '') in SOUTH_EXCEPTIONS:
        return 'South'

    # UK incode is always the last 3 characters; outcode is everything before that
    outcode = pc[:-3].strip() if len(pc) > 3 else pc.split(' ')[0]
    north_prefixes = {'N', 'NW', 'E', 'EN', 'HA', 'IG', 'RM', 'UB', 'WD', 'WC', 'EC', 'W'}
    # SW districts that sit north of the Thames
    north_sw_districts = {'1', '3', '5', '6', '7', '10'}
    # TW districts that sit north of the Thames
    # (TW7=Isleworth/WMX, TW8=Brentford, TW9=Kew, TW3-TW6=Hounslow/Heathrow, TW11=Teddington, TW12=Hampton, TW13-TW14=Feltham)
    north_tw_districts = {'1', '2', '3', '4', '5', '6', '7', '8', '11', '12', '13', '14'}

    # Extract only LEADING letters as the area code (WC2R → WC, EC1A → EC, SW1A → SW)
    prefix = ''
    for c in outcode:
        if c.isalpha():
            prefix += c
        else:
            break

    if prefix == 'SW':
        # Extract the district number from the outcode (SW1V → '1', SW10 → '10')
        district_num = ''.join(c for c in outcode[len(prefix):] if c.isdigit())
        return 'North' if district_num in north_sw_districts else 'South'

    if prefix == 'TW':
        # Extract the district number from the outcode (TW7 → '7', TW13 → '13')
        district_num = ''.join(c for c in outcode[len(prefix):] if c.isdigit())
        return 'North' if district_num in north_tw_districts else 'South'

    if prefix == 'KT':
        # Some KT sub-districts are north of the Thames:
        #   KT1 4xx (Hampton Wick) — must check incode to avoid catching KT14
        #   KT8 9xx (East Molesey, north bank) — must check incode to avoid catching KT89
        district_num = ''.join(c for c in outcode[len(prefix):] if c.isdigit())
        incode = pc.replace(' ', '')[-3:]
        if district_num == '1' and incode[0] == '4':
            return 'North'
        if district_num == '8' and incode[0] == '9':
            return 'North'
        return 'South'

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

def main():
    args = parse_args()

    output_dir = args.output_dir or os.path.join("output", args.profile)
    os.makedirs(output_dir, exist_ok=True)

    # 1. LOAD DATA
    hospitals = load_hospitals_for_profile(args.hospitals_csv, profile=args.profile)
    postcodes = pd.read_csv(args.postcodes_csv)
    print(f"Loaded {len(postcodes):,} postcodes and {len(hospitals)} hospitals for profile '{args.profile}'.")

    # 5. EXECUTION
    postcodes['Side'] = postcodes['Postcode'].apply(get_side)
    results = postcodes[['Postcode', 'Latitude', 'Longitude', 'Side']].copy()

    for side in ['North', 'South']:
        pc_group = postcodes[postcodes['Side'] == side]
        hosp_side = hospitals[hospitals['Side'].isin([side, 'Both'])]

        for label, level in [('Any', None), ('L1', 1), ('L2', 2), ('L3', 3)]:
            hosp_subset = hosp_side if level is None else hosp_side[hosp_side['Level'] == level]
            names, dists = find_nearest(pc_group, hosp_subset.reset_index(drop=True))
            results.loc[pc_group.index, f'Closest_{label}'] = names
            results.loc[pc_group.index, f'Distance_{label}_km'] = dists

    # 6. SAVE SEPARATE FILE PER HOSPITAL (based on Closest_Any)
    for hospital, group in results.groupby('Closest_Any'):
        safe_name = re.sub(r'[^\w\s-]', '', hospital).strip().replace(' ', '_')
        out_file = os.path.join(output_dir, f"{safe_name}.csv")
        group.to_csv(out_file, index=False)
        print(f"  → {out_file} ({len(group)} rows)")

    # 7. SAVE COMBINED FILE
    combined_file = os.path.join(output_dir, "All_Postcodes.csv")
    results.to_csv(combined_file, index=False)
    print(f"\n  → {combined_file} ({len(results)} rows)")
    print(f"\nDone! {len(results)} postcodes across {results['Closest_Any'].nunique()} hospital files + 1 combined file.")


if __name__ == '__main__':
    main()
