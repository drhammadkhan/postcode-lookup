from flask import Flask, render_template, request, jsonify, send_from_directory
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, 'docs')

# Load data once at startup
print("Loading data...")
all_postcodes = pd.read_csv('output/All_Postcodes.csv', dtype={'Postcode': str})
hospitals = pd.read_csv('hospitals_refined.csv')

# Build a lookup dict keyed by normalised postcode (no spaces, uppercase)
all_postcodes['_key'] = all_postcodes['Postcode'].str.replace(' ', '', regex=False).str.upper()
lookup = all_postcodes.set_index('_key')
print(f"Loaded {len(lookup):,} postcodes and {len(hospitals)} hospitals.")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/index.html')
def index_alias():
    return render_template('index.html')


@app.route('/extra-maps')
@app.route('/extra_maps.html')
def extra_maps():
    return send_from_directory(DOCS_DIR, 'extra_maps.html')


@app.route('/maps/<path:filename>')
def extra_maps_assets(filename):
    return send_from_directory(os.path.join(DOCS_DIR, 'maps'), filename)


@app.route('/postcodes.json')
def postcodes_json():
    return send_from_directory(DOCS_DIR, 'postcodes.json')


@app.route('/hospitals.json')
def hospitals_json():
    return send_from_directory(DOCS_DIR, 'hospitals.json')


@app.route('/search')
def search():
    raw = request.args.get('postcode', '').strip()
    pc_key = raw.replace(' ', '').upper()

    if not pc_key:
        return jsonify({'error': 'Please enter a postcode.'})

    if pc_key not in lookup.index:
        return jsonify({'error': f'Postcode "{raw}" not found.'})

    row = lookup.loc[pc_key]

    # Build hospital details for each level
    levels = []
    for label, name in [('Any', 'Any Level'), ('L1', 'Level 1 — Special Care'),
                         ('L2', 'Level 2 — High Dependency'), ('L3', 'Level 3 — NICU')]:
        hosp_name = row[f'Closest_{label}']
        dist = row[f'Distance_{label}_km']
        # Find hospital coords
        hosp_row = hospitals[hospitals['Hospital Name'] == hosp_name]
        hosp_lat = float(hosp_row['Latitude'].values[0]) if not hosp_row.empty else None
        hosp_lon = float(hosp_row['Longitude'].values[0]) if not hosp_row.empty else None
        # Include specialty tags for Level 3 units
        tags = ''
        if not hosp_row.empty and int(hosp_row['Level'].values[0]) == 3:
            raw_tags = hosp_row['Specialty Tags'].values[0]
            if pd.notna(raw_tags):
                tags = str(raw_tags).strip()
        levels.append({
            'label': name,
            'hospital': hosp_name,
            'distance_km': float(dist),
            'lat': hosp_lat,
            'lon': hosp_lon,
            'specialty_tags': tags,
        })

    return jsonify({
        'postcode': row['Postcode'],
        'lat': float(row['Latitude']),
        'lon': float(row['Longitude']),
        'side': row['Side'],
        'levels': levels,
    })


@app.route('/catchment-map')
def catchment_map():
    return render_template('catchment.html')


@app.route('/catchment-map-content')
def catchment_map_content():
    """Serve the generated catchment map HTML as raw content."""
    try:
        with open('neonatal_catchment_map.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return '<p style="padding:2rem;text-align:center;">Catchment map not yet generated. Run <code>python generate_map.py</code> first.</p>'


@app.route('/hospitals')
def get_hospitals():
    """Return all hospitals as JSON for the map."""
    data = []
    for _, row in hospitals.iterrows():
        data.append({
            'name': row['Hospital Name'],
            'level': int(row['Level']),
            'side': row['Side'],
            'lat': float(row['Latitude']),
            'lon': float(row['Longitude']),
        })
    return jsonify(data)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
