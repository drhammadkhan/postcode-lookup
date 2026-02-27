# Technical Explanation

A detailed, human-readable breakdown of how the postcode lookup script works, including the mathematics behind the distance calculations.

---

## Overview

The script takes ~326,000 London postcodes and ~34 neonatal hospitals, and for each postcode finds the nearest hospital at each care level (1, 2, 3, and any). It does this in three stages:

1. **Classify** each postcode as North or South of the Thames
2. **Search** for the nearest hospital using a spatial data structure (KD-tree)
3. **Measure** the actual distance using the Haversine formula

---

## Stage 1: Postcode Classification (North/South)

### What is an outcode?

A UK postcode like `SW1A 2AA` has two parts:

- **Outcode** (first half): `SW1A` — identifies the area and district
- **Incode** (second half): `2AA` — narrows it to a few addresses

The outcode itself has an **area code** (the leading letters) and a **district number**:

```
SW1A
││ │
││ └─ District sub-letter (not all outcodes have this)
│└── District number
└── Area code
```

### How the script extracts the area code

The script reads characters from the start of the outcode until it hits a digit:

```
WC2R → WC    (stops at '2')
EC1A → EC    (stops at '1')
SW10 → SW    (stops at '1')
N1C  → N     (stops at '1')
BR1  → BR    (stops at '1')
```

This is important because a naïve approach of stripping all digits (e.g. `WC2R` → `WCR`) would fail to match against the known prefix `WC`.

### The classification rules

The script uses a lookup set of area codes known to be north of the Thames:

```
N, NW, E, EN, HA, IG, RM, UB, WD, WC, EC, W
```

If the area code is in this set → **North**. Otherwise → **South**.

**Special case — SW postcodes:** The SW area straddles the river. Some districts (SW1, SW3, SW5, SW6, SW7, SW10) are north of the Thames (Chelsea, Knightsbridge, Earl's Court), while others (SW2, SW4, SW8, SW9, SW11–SW20) are south (Brixton, Clapham, Battersea). The script extracts the district number from the outcode and checks it against a known set of north-side districts.

---

## Stage 2: Nearest Neighbour Search (KD-Tree)

### The problem

Given a postcode at coordinates (lat, lon), find the closest hospital from a filtered subset. Doing this with brute force — calculating the distance to every hospital for every postcode — would mean 326,000 × 34 = ~11 million distance calculations, repeated for each care level.

### What is a KD-tree?

A **KD-tree** (k-dimensional tree) is a data structure that organises points in space so you can quickly find the nearest one without checking every point.

Think of it like a series of binary decisions:

1. Split all hospitals into two groups: those with latitude above the median and those below
2. Within each group, split by longitude
3. Keep splitting alternately by latitude and longitude

This creates a tree where nearby points end up in the same branches. To find the nearest hospital to a postcode, you descend the tree, only exploring branches that could contain a closer point than the best found so far. This reduces the search from O(n) to approximately O(log n).

### The longitude scaling problem

KD-trees use **Euclidean distance** — they treat the coordinate axes as a flat grid. But the Earth is a sphere, and lines of longitude converge towards the poles. At the equator, 1° of longitude spans ~111 km. At London's latitude (51.5°N), it only spans:

$$
111.12 \times \cos(51.5°) \approx 111.12 \times 0.6225 \approx 69.2 \text{ km}
$$

Meanwhile, 1° of latitude is always ~111 km regardless of where you are.

If we feed raw (lat, lon) into the KD-tree, it would think a hospital 1° east is the same distance as one 1° north — but in reality the eastward one is ~40% closer. This would give wrong nearest-neighbour results.

**The fix:** Before building the KD-tree, we scale longitude by $\cos(51.5°)$:

$$
\text{scaled\_lon} = \text{lon} \times \cos(51.5°)
$$

This makes the coordinate space approximately proportional to real-world distances, so the KD-tree finds the genuinely nearest hospital. We only use this scaling for the search — actual distances are calculated separately using the Haversine formula.

### Vectorisation

Instead of looping through 326,000 postcodes one at a time, the script:

1. Groups all postcodes by side (North/South)
2. For each side × level combination, builds **one** KD-tree
3. Queries it with **all** postcodes in that group at once

This means only **8 KD-tree builds** (2 sides × 4 levels) instead of ~1.3 million, reducing runtime from potentially hours to seconds.

---

## Stage 3: Distance Calculation (Haversine Formula)

### Why not just use Pythagoras?

On a flat surface, the distance between two points is:

$$
d = \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}
$$

But the Earth is a sphere (approximately). Over short distances in London this error is small, but the Haversine formula gives us accurate results without any flat-Earth approximation.

### The Haversine formula

Given two points with latitude and longitude in **radians**:

- Point 1: $(\phi_1, \lambda_1)$
- Point 2: $(\phi_2, \lambda_2)$

First, compute the intermediate value $a$:

$$
a = \sin^2\!\left(\frac{\phi_2 - \phi_1}{2}\right) + \cos(\phi_1) \cdot \cos(\phi_2) \cdot \sin^2\!\left(\frac{\lambda_2 - \lambda_1}{2}\right)
$$

Then the distance is:

$$
d = 2R \cdot \arcsin\!\left(\sqrt{a}\right)
$$

Where $R = 6{,}371$ km is the Earth's mean radius.

### What does this actually calculate?

The Haversine formula computes the **great-circle distance** — the shortest path between two points along the surface of a sphere. Imagine stretching a string taut between two points on a globe; that's the great-circle distance.

### Breaking down the maths intuitively

The value $a$ captures two components of separation:

- $\sin^2\!\left(\frac{\Delta\phi}{2}\right)$ — how far apart the points are in the north-south direction
- $\cos(\phi_1) \cdot \cos(\phi_2) \cdot \sin^2\!\left(\frac{\Delta\lambda}{2}\right)$ — how far apart they are east-west, **adjusted for latitude** (the $\cos$ terms shrink this component near the poles, where longitude lines converge)

The $\arcsin(\sqrt{a})$ converts this back into an angle (in radians), and multiplying by $2R$ gives the arc length in kilometres.

### Example

For postcode BR1 1AA (51.4015°N, 0.0154°E) and Princess Royal hospital (51.3856°N, 0.0455°E):

1. Convert to radians: $\phi_1 = 0.8974$, $\lambda_1 = 0.000269$, $\phi_2 = 0.8971$, $\lambda_2 = 0.000794$
2. $\Delta\phi = -0.000278$, $\Delta\lambda = 0.000525$
3. $a = \sin^2(-0.000139) + \cos(0.8974) \cdot \cos(0.8971) \cdot \sin^2(0.000263)$
4. $a \approx 1.93 \times 10^{-8} + 0.3876 \times 6.89 \times 10^{-8} \approx 4.60 \times 10^{-8}$
5. $d = 2 \times 6371 \times \arcsin(\sqrt{4.60 \times 10^{-8}}) \approx 2.73$ km

---

## Summary of the pipeline

```
postcodes_master.csv ──→ Classify N/S ──→ Group by side ──┐
                                                           ├──→ KD-tree query ──→ Haversine distance ──→ Output CSV
hospitals_refined.csv ──→ Filter by side & level ──────────┘
```

| Step | Method | Purpose |
|------|--------|---------|
| Classification | Prefix parsing | Assign postcodes to correct side of the Thames |
| Nearest search | KD-tree with scaled coordinates | Efficiently find the closest hospital |
| Distance | Haversine formula | Accurately measure real-world distance in km |
