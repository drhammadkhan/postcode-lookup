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

- **`hospitals_refined.csv`** — A list of ~34 neonatal hospitals across London, including their location (latitude/longitude), care level (1–3), and which side of the Thames they serve (North, South, or Both).
- **`postcodes_master.csv`** — A list of ~326,000 London-area postcodes with their geographic coordinates.

It then runs through three steps:

### 1. North or South of the River?

London's neonatal care is broadly organised around the River Thames. The script classifies each postcode as being on the **North** or **South** side based on its area code (the letters at the start of the postcode).

The outcode is extracted by stripping the last 3 characters (the incode) from the postcode, which correctly handles postcodes with or without spaces.

**SW postcodes** are handled specially — districts SW1, SW3, SW5, SW6, SW7 and SW10 are classified as North, while the rest are South. A small number of individual postcodes within those North districts are manually overridden as South (see `TECHNICAL.md` for the full list).

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

A separate script (`generate_map.py`) generates an interactive HTML map showing each hospital's catchment area as colour-coded dots. Hover over any dot to see its postcode. Hospital markers can be clicked for name, level and side. Use the layer control (top-right) to toggle individual hospitals on/off.

## How to run it

1. Make sure you have Python 3 installed
2. Install the required packages:
   ```
   pip install pandas numpy scipy folium
   ```
3. Place `hospitals_refined.csv` and `postcodes_master.csv` in the same folder as the script
4. Run the lookup:
   ```
   python postcode_lookup.py
   ```
5. Results will be saved to the `output/` folder
6. To generate the catchment map:
   ```
   python generate_map.py
   ```
7. Open `neonatal_catchment_map.html` in a browser