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

- **`hospitals_refined.csv`** — A list of ~34 neonatal hospitals across London, including their location (latitude/longitude), care level (1–3), and which side of the Thames they serve.
- **`postcodes_master.csv`** — A list of ~326,000 London-area postcodes with their geographic coordinates.

It then runs through three steps:

### 1. North or South of the River?

London's neonatal care is broadly organised around the River Thames. The script classifies each postcode as being on the **North** or **South** side based on its area code (the letters at the start of the postcode). Some hospitals near the river borders serve both sides.

### 2. Find the nearest hospitals

For each postcode, the script finds the closest neonatal hospital on the same side of the river, using accurate geographic distance calculations ([Haversine formula](https://en.wikipedia.org/wiki/Haversine_formula)). It does this four times:

- Closest unit at **any level**
- Closest **Level 1** (Special Care)
- Closest **Level 2** (High Dependency)
- Closest **Level 3** (NICU)

### 3. Output the results

The results are saved to **`Neonatal_Lookup_Final.csv`** with one row per postcode:

| Column | Example |
|--------|---------|
| Postcode | BR1 1AA |
| Side | South |
| Closest_Any | Princess Royal (PRUH) (5.05km) |
| Closest_L1 | Darent Valley (17.28km) |
| Closest_L2 | Princess Royal (PRUH) (5.05km) |
| Closest_L3 | Kings College Hospital (10.51km) |

## How to run it

1. Make sure you have Python 3 installed
2. Install the required packages:
   ```
   pip install pandas numpy scipy
   ```
3. Place `hospitals_refined.csv` and `postcodes_master.csv` in the same folder as the script
4. Run:
   ```
   python postcode_lookup.py
   ```
5. The output will be saved as `Neonatal_Lookup_Final.csv`