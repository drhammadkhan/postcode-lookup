#!/usr/bin/env python3
"""
change_summary.py - say what a rebuild actually changed.

Compares the current generated files with a git ref (default HEAD, i.e. the
last commit) and prints:
  * hospital reference changes (level, side, tags, ...) from hospitals_refined.csv
  * how many postcodes changed hospital at each care level, and where they moved
  * catchment population / births per hospital and level (before -> after)

    python3 change_summary.py                 # compare with HEAD
    python3 change_summary.py --against main  # compare with another ref
    python3 change_summary.py --out summary.md

build_all.py runs this at the end of every build.
"""

import argparse
import io
import json
import os
import subprocess
import sys

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEVELS = [("Any", "Closest_Any"), ("L1", "Closest_L1"), ("L2", "Closest_L2"), ("L3", "Closest_L3")]


def git_show(ref, path):
    """Contents of `path` at `ref`, or None if it did not exist."""
    try:
        return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=BASE_DIR,
                                       stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return None


def read_csv_at(ref, path, **kw):
    raw = git_show(ref, path)
    return None if raw is None else pd.read_csv(io.BytesIO(raw), **kw)


def read_json_at(ref, path):
    raw = git_show(ref, path)
    return None if raw is None else json.loads(raw)


def hospital_changes(ref):
    old = read_csv_at(ref, "hospitals_refined.csv")
    new = pd.read_csv(os.path.join(BASE_DIR, "hospitals_refined.csv"))
    lines = []
    if old is None:
        return ["hospitals_refined.csv is new."]
    old, new = old.set_index("Hospital Name"), new.set_index("Hospital Name")
    for name in sorted(set(new.index) - set(old.index)):
        lines.append(f"+ added **{name}** (level {new.loc[name, 'Level']}, {new.loc[name, 'Side']})")
    for name in sorted(set(old.index) - set(new.index)):
        lines.append(f"- removed **{name}**")
    for name in sorted(set(old.index) & set(new.index)):
        for col in [c for c in new.columns if c in old.columns]:
            a, b = old.loc[name, col], new.loc[name, col]
            if not (pd.isna(a) and pd.isna(b)) and str(a) != str(b):
                lines.append(f"~ **{name}**: {col} {a} -> {b}")
    return lines or ["No hospital reference changes."]


def assignment_changes(ref, profile):
    path = f"output/{profile}/All_Postcodes.csv"
    old = read_csv_at(ref, path, dtype=str)
    if old is None:
        return [f"`{path}` has no previous version to compare with."]
    new = pd.read_csv(os.path.join(BASE_DIR, path), dtype=str)
    if len(old) != len(new) or not (old["Postcode"].values == new["Postcode"].values).all():
        return [f"Postcode list changed ({len(old):,} -> {len(new):,} rows); per-postcode comparison skipped."]
    lines = []
    for label, col in LEVELS:
        a, b = old[col].fillna("None"), new[col].fillna("None")
        moved = a != b
        n = int(moved.sum())
        if not n:
            lines.append(f"- {label}: no postcodes changed")
            continue
        flows = (pd.DataFrame({"from": a[moved], "to": b[moved]}).value_counts().head(6))
        detail = "; ".join(f"{f} -> {t} ({c:,})" for (f, t), c in flows.items())
        lines.append(f"- {label}: **{n:,}** postcodes changed ({n / len(new):.1%}): {detail}")
    return lines


def total_changes(ref, path, key, fields):
    old, new = read_json_at(ref, path), json.load(open(os.path.join(BASE_DIR, path), encoding="utf-8"))
    if old is None:
        return [f"`{path}` has no previous version."]
    old, new = {r[key]: r for r in old}, {r[key]: r for r in new}
    lines = []
    for name in sorted(set(old) | set(new)):
        diffs = []
        for f in fields:
            a, b = old.get(name, {}).get(f, 0), new.get(name, {}).get(f, 0)
            if a != b:
                diffs.append(f"{f.replace('_population', '').replace('_births', '')}: {a:,} -> {b:,}")
        if diffs:
            lines.append(f"- {name}: " + ", ".join(diffs))
    return lines or ["- no changes"]


def build_summary(ref):
    out = [f"# Rebuild summary (compared with `{ref}`)", "", "## Hospital reference data", ""]
    out += hospital_changes(ref)
    for profile in ("lookup", "analysis"):
        out += ["", f"## Postcode assignments: {profile} profile", ""] + assignment_changes(ref, profile)
    out += ["", "## Catchment populations (analysis profile)", ""]
    out += total_changes(ref, "docs/populations.json", "hospital",
                         ["any_population", "l1_population", "l2_population", "l3_population"])
    out += ["", "## Catchment births (analysis profile)", ""]
    out += total_changes(ref, "docs/births.json", "hospital",
                         ["any_births", "l1_births", "l2_births", "l3_births"])
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--against", default="HEAD", help="git ref to compare with (default HEAD)")
    ap.add_argument("--out", help="also write the summary to this file")
    args = ap.parse_args()
    summary = build_summary(args.against)
    print(summary)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(summary)


if __name__ == "__main__":
    sys.exit(main())
