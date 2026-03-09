# Neonatal Unit Postcode Lookup

## What does this project do?

This tool helps answer a simple but important question: **for any given London postcode, which is the nearest neonatal (newborn baby) hospital unit?**

When a baby is born prematurely or becomes seriously ill, they may need specialist care in a **Neonatal Unit**. These units are graded into three levels:

| Level | Name | What it provides |
|-------|------|------------------|
| **Level 1** | Special Care | Short-term support for babies who need extra monitoring |
| **Level 2** | High Dependency | More intensive support, including help with breathing |
| **Level 3** | Neonatal Intensive Care (NICU) | The highest level of care for the most critically ill babies |

Not every hospital has every level of unit, so knowing which is closest — and at which level — matters.

## How does it work?

The script takes two input files:

- **`hospitals_refined.csv`** — A list of ~31 neonatal hospitals across London, including their location (latitude/longitude), care level (1–3), and which side of the Thames they serve (North, South, or Both).
- **`postcodes_master.csv`** — A list of ~326,000 London-area postcodes with their geographic coordinates.

It then runs through three steps:

### 1. North or South of the River?

London's neonatal care is broadly organised around the River Thames. The script classifies each postcode as being on the **North** or **South** side based on its area code (the letters at the start of the postcode).

The outcode is extracted by stripping the last 3 characters (the incode) from the postcode, which correctly handles postcodes with or without spaces.

**SW postcodes** are handled specially — districts SW1, SW3, SW5, SW6, SW7 and SW10 are classified as North, while the rest are South. A small number of individual postcodes within those North districts are manually overridden as South (see `TECHNICAL.md` for the full list).

**TW postcodes** are also split by district. Districts TW1–TW9 and TW11–TW14 (Twickenham, Hounslow, Heathrow, Brentford, Kew, Isleworth, Teddington, Hampton, Feltham) sit north of the Thames; TW10 (Richmond south) sits south.

**KT postcodes** are mostly south of the Thames, but two sub-groups are north:
- **KT1 4xx** — Hampton Wick (north bank, near Kingston Bridge)
- **KT8 9xx** — East Molesey (north bank)

These are identified by checking the incode (the last three characters of the full postcode) to avoid false matches against similar outcodes like KT14.

Some hospitals near the river serve **both** sides (e.g. West Middlesex), so they are available to postcodes on either side.

### 2. Find the nearest hospitals

For each postcode, the script finds the closest neonatal hospital on the same side of the river, using accurate geographic distance calculations ([Haversine formula](https://en.wikipedia.org/wiki/Haversine_formula)). It does this four times:

- Closest unit at **any level**
- Closest **Level 1** (Special Care)
- Closest **Level 2** (High Dependency)
- Closest **Level 3** (NICU)

### 3. Output the results

Results are saved to the `output/` folder in two formats:

**Individual hospital files** — one CSV per hospital (e.g. `output/West_Middlesex.csv`), containing all postcodes where that hospital is the nearest at any level.

**Combined file** — `output/All_Postcodes.csv` with one row per postcode:

| Column | Example |
|--------|---------|
| Postcode | TW7 6QT |
| Latitude | 51.4729 |
| Longitude | -0.3317 |
| Side | South |
| Closest_Any | West Middlesex |
| Distance_Any_km | 0.48 |
| Closest_L1 | West Middlesex |
| Distance_L1_km | 0.48 |
| Closest_L2 | Kingston Hospital |
| Distance_L2_km | 7.32 |
| Closest_L3 | St. Georges Hospital |
| Distance_L3_km | 12.0 |

### 4. Visualise on a map

A separate script (`generate_map.py`) generates an interactive HTML map showing each hospital's catchment area as colour-coded dots. Hover over any dot to see its postcode. Hospital markers can be clicked for name, level and side. Use the layer control (top-right) to toggle individual hospitals on/off. A **Deselect All / Select All** button at the bottom of the control panel lets you quickly clear or restore all layers.

Before plotting, three filters suppress postcodes with incorrect OS coordinates that would appear on the wrong side of the river:

- **Cluster filter** — any coordinate shared by more than 50 postcodes in the full dataset (large-user/PO Box entries where OS assigns hundreds of postcodes to a single wrong grid reference).
- **Thames polygon filter** — uses a [Shapely](https://shapely.readthedocs.io/) polygon tracing the south bank of the Thames from Hampton to Greenwich. A North-assigned postcode whose coordinate falls inside this polygon has a wrong/non-geographic OS grid reference and is suppressed. The polygon traces the actual meandering riverbank, so legitimate north-bank Fulham/Chelsea addresses (SW6, SW10, SW3) are correctly kept.
- **Manual override list** (`MAP_SUPPRESS`) — individual postcodes with wrong coordinates in the opposite direction (South-assigned but plotted north of the river), e.g. SW9 7RT.

### 5. Local web app (Flask)

A Flask-based frontend (`app.py`) provides a local web interface at `http://127.0.0.1:5001` with:

- **Postcode search** — enter any London postcode to see the nearest neonatal unit at each level, with distances and an interactive map.
- **Embedded catchment map** — the generated map is viewable directly within the app.
- **Hospital API** — a `/hospitals` endpoint returning all hospitals as JSON.

### 6. Static site (GitHub Pages)

A fully client-side version lives in the `docs/` folder and is published via GitHub Pages at **https://drhammadkhan.github.io/postcode-lookup/**.

The script `build_static.py` compresses the output into two compact JSON files (`docs/postcodes.json` and `docs/hospitals.json`) which `docs/index.html` loads and searches entirely in the browser — no server required.

## How to run it

### Prerequisites

1. Make sure you have Python 3 installed (use `python3` on macOS)
2. Install the required packages:
   ```
   pip install pandas numpy scipy folium flask shapely
   ```
3. Confirm the input files are present in the project root:
   - `hospitals_refined.csv`
   - `postcodes_master.csv`

### Run each script (explicit commands)

1. **Generate postcode lookups (main pipeline)**
   ```
   python3 postcode_lookup.py
   ```
   - Outputs:
     - `output/All_Postcodes.csv`
     - One CSV per hospital in `output/`

2. **Generate the interactive catchment map**
   ```
   python3 generate_map.py
   ```
   - Output:
     - `neonatal_catchment_map.html`

3. **Build the static JSON for the GitHub Pages / Netlify site**
   ```
   python3 build_static.py
   ```
   - Outputs:
     - `docs/postcodes.json`
     - `docs/hospitals.json`

4. **Run the local Flask web app**
   ```
   python3 app.py
   ```
   - Then visit `http://127.0.0.1:5001` in your browser

5. **Open the map directly (optional)**
   - Open `neonatal_catchment_map.html` in your browser

### Local script runner (separate UI)

If you want a small local frontend with buttons to run each script (or the full pipeline), start the runner:

```
python3 script_runner_app.py
```

Then open `http://127.0.0.1:5002` in your browser and use the buttons to run:
- `postcode_lookup.py`
- `generate_map.py`
- `build_static.py`
- or the full pipeline in order