#!/usr/bin/env python3
"""
equalise_catchments.py

Redistributes London postcodes across neonatal hospitals to achieve roughly
equal populations per catchment, while:

  • Respecting the North/South Thames boundary
  • Producing geographically compact catchment areas

Algorithm — Weighted Voronoi + Geographic Cleanup
──────────────────────────────────────────────────
Phase 1 — Iterative weighted Voronoi:
  Each postcode is assigned to argmin_h( dist(p,h) / s_h ).
  Scale factors s_h are updated to grow under-populated hospitals and shrink
  over-populated ones until balance converges to ±1%.
  A relative-distance locality mask (ratio ≤ MAX_RATIO) prevents hospitals
  from leaping over closer neighbours.

Phase 2 — Geographic cleanup:
  Any postcode assigned to hospital H, where a closer hospital H2 exists
  AND swapping would not push H2 more than SWAP_TOL over target, is
  re-assigned to H2. This ensures the natural "nearest wins" principle is
  respected for all but the most constrained balance cases.
"""

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

# ── Configuration ─────────────────────────────────────────────────────────────

ALL_POSTCODES_CSV = "output/All_Postcodes.csv"
POPULATION_CSV    = "pcd_p001.csv"
HOSPITALS_CSV     = "hospitals_refined.csv"
OUTPUT_CSV        = "output/All_Postcodes_Equalised.csv"
SUMMARY_CSV       = "output/Equalised_Summary.csv"

BALANCE_ON = "population"   # "population" | "births"

# London mean latitude for lon→km scaling
COS_LAT = np.cos(np.radians(51.5))

# ── Helpers ───────────────────────────────────────────────────────────────────

def scaled_xy(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """[lat, lon * cos(51.5°)] — makes Euclidean ≈ real distance near London."""
    return np.column_stack([lats, lons * COS_LAT])


# ── Load data ─────────────────────────────────────────────────────────────────

print("Loading data …")

pc_df = pd.read_csv(ALL_POSTCODES_CSV)
pc_df["Postcode"] = pc_df["Postcode"].str.strip()

pop_raw = pd.read_csv(POPULATION_CSV)
pop_raw["Postcode"] = pop_raw["Postcode"].str.strip()
population_by_pc = pop_raw.groupby("Postcode")["Count"].sum()
pc_df["population"] = pc_df["Postcode"].map(population_by_pc).fillna(0).astype(int)

hosp_df = pd.read_csv(HOSPITALS_CSV)
hosp_df["Hospital Name"] = hosp_df["Hospital Name"].str.strip()

print(f"  {len(pc_df):,} postcodes  |  {len(hosp_df)} hospital rows  |  balancing on: {BALANCE_ON}")

# ── Process each side independently ──────────────────────────────────────────

all_results   = []
all_summaries = []

for side in ("North", "South"):
    print(f"\n{'─'*60}\n  {side} side\n{'─'*60}")

    pc = pc_df[pc_df["Side"] == side].copy().reset_index(drop=True)
    n_pc = len(pc)

    hosp = (
        hosp_df[hosp_df["Side"].isin([side, "Both"])]
        .groupby("Hospital Name", as_index=False)
        .first()
        .reset_index(drop=True)
    )
    n_hosp = len(hosp)

    pc_xy   = scaled_xy(pc["Latitude"].values, pc["Longitude"].values)
    hosp_xy = scaled_xy(hosp["Latitude"].values, hosp["Longitude"].values)
    weights = pc[BALANCE_ON].values.astype(np.float64)

    # ── Drop geographically absent hospitals ────────────────────────────────
    # A hospital listed as "Both" may have its physical location on the other
    # side (e.g. Wexham Park is in the North). Detect by Voronoi: hospitals
    # that attract zero postcodes in the nearest-hospital assignment are absent.
    hosp_tree = cKDTree(hosp_xy)
    _, nn = hosp_tree.query(pc_xy)
    voronoi_counts = np.bincount(nn, minlength=n_hosp)
    absent = np.where(voronoi_counts == 0)[0]
    if len(absent):
        print(f"  Dropping {len(absent)} absent hospitals: "
              f"{hosp['Hospital Name'].iloc[absent].tolist()}")
        keep = np.where(voronoi_counts > 0)[0]
        hosp    = hosp.iloc[keep].reset_index(drop=True)
        hosp_xy = hosp_xy[keep]
        n_hosp  = len(hosp)
        hosp_tree = cKDTree(hosp_xy)

    total_weight = weights.sum()
    target       = total_weight / n_hosp
    print(f"  {n_pc:,} postcodes  |  {n_hosp} hospitals  |  target = {target:,.0f}")

    # ── Phase 1: Iterative weighted Voronoi ─────────────────────────────────
    print("  Computing distance matrix …", end=" ", flush=True)
    from scipy.spatial.distance import cdist as _cdist
    D = _cdist(pc_xy, hosp_xy).astype(np.float32)   # (n_pc, n_hosp)
    print(f"  {D.shape[0]:,} × {D.shape[1]}  ({D.nbytes / 1e6:.0f} MB)")

    # KNN locality mask: each postcode may only go to its K nearest hospitals.
    # K=3 for small pools (≤10), K=4 for larger pools (16).
    KNN_K    = min(3 if n_hosp <= 10 else 4, n_hosp)
    knn_rank = np.argsort(D, axis=1)
    top_k    = np.zeros((n_pc, n_hosp), dtype=bool)
    top_k[np.arange(n_pc)[:, None], knn_rank[:, :KNN_K]] = True
    D_masked = D.copy()
    D_masked[~top_k] = np.inf
    print(f"  KNN mask: K={KNN_K}")

    s   = np.ones(n_hosp, dtype=np.float64)
    lr  = 0.08
    best_assignment = None
    best_max_dev    = np.inf
    stall_count     = 0

    print(f"  {'Iter':>5}  {'MaxDev':>8}  {'MeanDev':>9}")
    print(f"  {'─'*5}  {'─'*8}  {'─'*9}")

    for it in range(300):
        inv_s      = (1.0 / s).astype(np.float32)
        assignment = np.argmin(D_masked * inv_s[np.newaxis, :], axis=1).astype(np.int32)
        assigned_wt = np.array([weights[assignment == h].sum() for h in range(n_hosp)],
                               dtype=np.float64)
        devs     = assigned_wt / target - 1.0
        max_dev  = np.abs(devs).max()
        mean_dev = np.abs(devs).mean()

        if it % 20 == 0:
            print(f"  {it:>5}  {max_dev*100:>7.1f}%  {mean_dev*100:>8.1f}%")

        if max_dev < best_max_dev:
            best_max_dev    = max_dev
            best_assignment = assignment.copy()
            stall_count     = 0
        else:
            stall_count += 1
            lr *= 0.97

        if max_dev < 0.01 or stall_count > 40:
            break

        step = np.clip(lr * devs, -0.30, 0.30)
        s   /= np.exp(step)
        s    = np.clip(s, 0.01, 100.0)

    assignment  = best_assignment.copy()
    assigned_wt = np.array([weights[assignment == h].sum() for h in range(n_hosp)],
                           dtype=np.float64)
    print(f"  Phase 1 done: max dev = {best_max_dev*100:.2f}%")

    # ── Phase 2: Geographic cleanup ──────────────────────────────────────────
    # For each postcode assigned to H where a closer hospital H2 exists,
    # swap to H2 IF both hospitals stay within ±PHASE2_TOL of target.
    # Sort by distance saved (largest gain first).
    PHASE2_TOL = 0.20   # allow balance to shift by up to ±20% from Phase-1 result
    nearest_h  = D.argmin(axis=1).astype(np.int32)
    mismatch   = np.where(nearest_h != assignment)[0]

    if len(mismatch):
        dist_saved = (D[mismatch, assignment[mismatch]]
                      - D[mismatch, nearest_h[mismatch]])
        order    = np.argsort(-dist_saved)
        mismatch = mismatch[order]

        n_swapped = 0
        for p in mismatch:
            h_old = int(assignment[p])
            h_new = int(nearest_h[p])
            w     = weights[p]
            new_wt_old = assigned_wt[h_old] - w
            new_wt_new = assigned_wt[h_new] + w
            # Both hospitals must stay within ±PHASE2_TOL of target
            if (new_wt_new / target <= 1.0 + PHASE2_TOL and
                    new_wt_old / target >= 1.0 - PHASE2_TOL):
                assignment[p]       = h_new
                assigned_wt[h_old]  = new_wt_old
                assigned_wt[h_new]  = new_wt_new
                n_swapped          += 1

        post_devs   = assigned_wt / target - 1.0
        post_maxdev = np.abs(post_devs).max()
        print(f"  Phase 2 done: {n_swapped:,} postcodes moved to nearest  |  max dev = {post_maxdev*100:.2f}%")




    # Any unassigned postcodes (shouldn't happen) → nearest hospital
    leftover = np.where(assignment == -1)[0]
    if len(leftover):
        print(f"  Fallback: assigning {len(leftover)} unassigned postcodes")
        _, h_idx = hosp_tree.query(pc_xy[leftover])
        for i, p in enumerate(leftover):
            assignment[p] = int(h_idx[i])

    # ── Summary ──────────────────────────────────────────────────────────────
    pc = pc.copy()
    pc["New_Hospital"] = hosp["Hospital Name"].iloc[assignment].values

    summary = (
        pc.groupby("New_Hospital")
        .agg(Assigned_Weight=(BALANCE_ON, "sum"), Postcode_Count=("Postcode", "count"))
        .reset_index()
        .rename(columns={"New_Hospital": "Hospital"})
    )
    summary["Side"]           = side
    summary["Target"]         = target
    summary["Pct_vs_Target"]  = (summary["Assigned_Weight"] - target) / target * 100
    summary["Balance_Metric"] = BALANCE_ON

    all_results.append(pc)
    all_summaries.append(summary)

    print(f"\n  {'Hospital':<42} {'Assigned':>10}  {'Target':>10}  {'Δ%':>7}  {'Postcodes':>9}")
    print(f"  {'─'*42} {'─'*10}  {'─'*10}  {'─'*7}  {'─'*9}")
    for _, row in summary.sort_values("Assigned_Weight", ascending=False).iterrows():
        print(f"  {row['Hospital']:<42} {row['Assigned_Weight']:>10,.0f}  "
              f"{target:>10,.0f}  {row['Pct_vs_Target']:>+6.1f}%  "
              f"{row['Postcode_Count']:>9,}")

# ── Write outputs ─────────────────────────────────────────────────────────────

print(f"\n{'─'*60}\nWriting outputs …")

combined = pd.concat(all_results, ignore_index=True)
out = pc_df.copy()
out["New_Hospital"] = out["Postcode"].map(combined.set_index("Postcode")["New_Hospital"])
out.to_csv(OUTPUT_CSV, index=False)
print(f"  {OUTPUT_CSV}  ({len(out):,} rows)")

summary_df = pd.concat(all_summaries, ignore_index=True)[
    ["Side", "Hospital", "Balance_Metric", "Target",
     "Assigned_Weight", "Pct_vs_Target", "Postcode_Count"]
]
summary_df.to_csv(SUMMARY_CSV, index=False)
print(f"  {SUMMARY_CSV}  ({len(summary_df)} hospitals)")

print("\nOverall balance statistics:")
for side in ("North", "South"):
    s = summary_df[summary_df["Side"] == side]
    print(f"  {side}: max ±{s['Pct_vs_Target'].abs().max():.1f}%  "
          f"mean {s['Pct_vs_Target'].abs().mean():.1f}%  "
          f"std {s['Pct_vs_Target'].std():.1f}%")

print("\nDone.")
