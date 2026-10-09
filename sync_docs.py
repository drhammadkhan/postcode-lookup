#!/usr/bin/env python3
"""
sync_docs.py - keep numbers and examples in README.md / TECHNICAL.md in step with the data.

Doc text marks generated spots like this (invisible when rendered):

    ~<!--auto:postcodes_k-->333,000<!--/auto--> London-area postcodes

This script recomputes each value from the data files and rewrites the marked
spans.  Run it after a build (build_all.py does), or with --check to fail if a
doc is out of date (used by the tests and CI).
"""

import argparse
import csv
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS = ["README.md", "TECHNICAL.md"]
EXAMPLE_POSTCODE = "TW76QT"          # the worked example in the README
MARKER = re.compile(r"<!--auto:(\w+)-->(.*?)<!--/auto-->", re.DOTALL)


def _path(*parts):
    return os.path.join(BASE_DIR, *parts)


def _count_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1


def compute_values():
    with open(_path("hospitals_refined.csv"), newline="", encoding="utf-8") as f:
        hospitals = list(csv.DictReader(f))
    postcodes = _count_rows(_path("postcodes_master.csv"))
    outcodes = json.load(open(_path("docs", "outcode_map.json"), encoding="utf-8"))["outward_to_hospitals"]
    outcode_hospitals = {h for hs in outcodes.values() for h in hs}
    pops = json.load(open(_path("docs", "populations.json"), encoding="utf-8"))
    births = json.load(open(_path("docs", "births.json"), encoding="utf-8"))
    out_pops = json.load(open(_path("docs", "outcode_populations.json"), encoding="utf-8"))
    out_births = json.load(open(_path("docs", "outcode_births.json"), encoding="utf-8"))

    example = None
    with open(_path("output", "lookup", "All_Postcodes.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Postcode"].replace(" ", "") == EXAMPLE_POSTCODE:
                example = row
                break
    if example is None:
        raise SystemExit(f"Example postcode {EXAMPLE_POSTCODE} not found in output/lookup/All_Postcodes.csv")
    pc = example["Postcode"]
    pc = pc if " " in pc else pc[:-3] + " " + pc[-3:]
    cells = [
        ("Postcode", pc), ("Latitude", f"{float(example['Latitude']):.4f}"),
        ("Longitude", f"{float(example['Longitude']):.4f}"), ("Side", example["Side"]),
    ] + [(k, example[k]) for k in (
        "Closest_Any", "Distance_Any_km", "Closest_L1", "Distance_L1_km",
        "Closest_L2", "Distance_L2_km", "Closest_L3", "Distance_L3_km")]
    table = "\n| Column | Example |\n|--------|---------|\n" + "".join(f"| {k} | {v} |\n" for k, v in cells)

    n = len(hospitals)
    return {
        "hospitals": str(n),
        "postcodes": f"{postcodes:,}",
        "postcodes_k": f"{round(postcodes, -3):,}",
        "brute_force_m": f"{round(postcodes * n / 1e6)}",
        "outcodes": str(len(outcodes)),
        "outcode_hospitals": str(len(outcode_hospitals)),
        "population_total": f"{sum(r['any_population'] for r in pops):,}",
        "births_total": f"{sum(r['any_births'] for r in births):,}",
        "outcode_population_total": f"{sum(r['population'] for r in out_pops):,}",
        "outcode_births_total": f"{sum(r['births'] for r in out_births):,}",
        "example_row": table,
    }


def render(text, values, name):
    def sub(m):
        key = m.group(1)
        if key not in values:
            raise SystemExit(f"{name}: unknown auto key '{key}'. Known: {', '.join(values)}")
        return f"<!--auto:{key}-->{values[key]}<!--/auto-->"
    return MARKER.sub(sub, text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if any doc is out of date (writes nothing)")
    args = ap.parse_args()

    values = compute_values()
    stale = []
    for name in DOCS:
        with open(_path(name), encoding="utf-8", newline="") as f:
            old = f.read()
        new = render(old, values, name)
        if new != old:
            stale.append(name)
            if not args.check:
                with open(_path(name), "w", encoding="utf-8", newline="") as f:
                    f.write(new)
    if args.check and stale:
        print("Out of date: " + ", ".join(stale) + "  (run: python3 sync_docs.py)")
        sys.exit(1)
    print("Docs up to date." if not stale or args.check else "Updated: " + ", ".join(stale))


if __name__ == "__main__":
    main()
