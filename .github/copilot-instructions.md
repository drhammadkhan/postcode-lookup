# Copilot Instructions — Neonatal Postcode Lookup

## Project Overview
A London neonatal unit catchment tool: given a postcode it returns the nearest hospital at each care level (Any / L1 Special Care / L2 High Dependency / L3 NICU), honouring a strict North/South-of-Thames boundary. The front end lives in `docs/` and is served both by GitHub Pages / Netlify and by the local Flask app.

## Architecture & Data Flow

```
postcodes_master.csv  ─┐
hospitals_refined.csv  ─┴─→ postcode_lookup.py ──→ output/All_Postcodes.csv
                                                         │
                              build_static.py ←──────────┘
                                    │
                              docs/postcodes.json   (compact indexed lookup)
                              docs/hospitals.json
                                    │
                                    │
                              docs/index.html
                                    │
                         GitHub Pages / Flask
```

- **`postcode_lookup.py`** — main pipeline; run once to regenerate `output/`.
- **`build_static.py`** — converts `output/All_Postcodes.csv` into compact JSON for the browser.
- **`generate_map.py`** — produces `neonatal_catchment_map.html` (standalone Folium map).
- **`generate_extra_maps.py`** — writes the five thematic maps inside `docs/maps/`.
- **`app.py`** — Flask server; serves `docs/index.html` and static docs assets locally, with legacy JSON/API routes that read `output/All_Postcodes.csv` at startup.

## Key Developer Commands

```bash
python3 postcode_lookup.py        # regenerate output/ CSVs (~326k postcodes)
python3 build_static.py           # regenerate docs/postcodes.json + docs/hospitals.json
python3 generate_map.py           # regenerate neonatal_catchment_map.html
python3 generate_extra_maps.py    # regenerate docs/maps/map1_*.html … map5_*.html
python3 app.py                    # Flask dev server → http://127.0.0.1:5001
python3 script_runner_app.py      # pipeline web UI (no terminal needed) → http://127.0.0.1:5002
```

Always run `build_static.py` after `postcode_lookup.py` before testing the static site.

`script_runner_app.py` is a stdlib-only HTTP server (no Flask) on port **5002** that provides a browser UI for running `postcode_lookup.py`, `generate_map.py`, and `build_static.py` in sequence, with live log streaming. Use it when you want to trigger the pipeline without a terminal.

## Critical Domain Conventions

### North/South river classification (`postcode_lookup.py`)
- Outward codes starting with `SW`, `TW`, `KT` default to **South**; all others default to **North**.
- `SOUTH_EXCEPTIONS` (hardcoded set) overrides South→North for specific postcodes.
- Hospital rows have a `Side` column: `North`, `South`, or `Both`; a postcode only considers hospitals whose side matches or is `Both`.

### `postcodes.json` compact format
Each postcode record is a 12-element array (index → meaning):
```
[0] postcode string
[1] lat (4dp)  [2] lon (4dp)
[3] side (0=North, 1=South)
[4] any_idx  [5] any_dist_km
[6] l1_idx   [7] l1_dist_km
[8] l2_idx   [9] l2_dist_km
[10] l3_idx  [11] l3_dist_km
```
`*_idx` values are indices into the `names` array at the top of the JSON.

### Map suppression (non-geographic postcodes)
Three filters prevent OS-coordinate errors from appearing on the wrong river bank:
1. **Cluster** — postcodes whose `Closest_Any` hospital has < 5 nearby neighbours (statistical outlier).
2. **Polygon** — `SOUTH_OF_THAMES` Shapely polygon in `build_static.py` (hardcoded lon/lat vertices).
3. **Manual** — `MAP_SUPPRESS` set (e.g. `{'SW97RT'}`).

### Sector colour palette
Hospitals are grouped into sectors: `NC`, `NE`, `NW`, `SE`, `SW`, `Border`. Each sector uses an HSL hue range. The same `SECTOR_RANGES` dict is duplicated in `generate_extra_maps.py`, `docs/index.html`, and the generated map HTML — keep all copies in sync when changing colours.

## Input Files
| File | Purpose |
|---|---|
| `hospitals_refined.csv` | ~31 hospitals; columns: `Hospital Name`, `Latitude`, `Longitude`, `Level` (1/2/3), `Side`, `Sector`, `Specialty Tags` |
| `postcodes_master.csv` | ~326k postcodes; columns: `Postcode`, `Latitude`, `Longitude` |

## Deployment
The static front-end is published via **GitHub Pages** from the `docs/` directory. To publish an update:
1. Run `python3 postcode_lookup.py` then `python3 build_static.py` to regenerate `docs/postcodes.json` and `docs/hospitals.json`.
2. Commit and push `docs/` to the `main` branch — GitHub Pages serves it automatically.

No CI pipeline exists; regeneration and publishing are always manual steps.

## Static Site And Flask
- **Static (`docs/`)**: canonical front end; JS fetches `postcodes.json` and searches client-side. Deploy by pushing `docs/` to GitHub Pages (see repository Pages settings).
- **Flask (`app.py`)**: local server for the same `docs/index.html` and docs assets. Legacy routes such as `/search?postcode=TW76QT` still return JSON from `output/All_Postcodes.csv`.
