#!/usr/bin/env python3
"""
build_all.py - rebuild every generated file in the right order.

    python3 build_all.py                 # run everything
    python3 build_all.py --list          # show the steps, inputs and outputs
    python3 build_all.py --changed       # skip steps whose outputs are newer than their inputs
    python3 build_all.py --only maps     # run steps whose name contains 'maps'
    python3 build_all.py --from analysis # run from the 'analysis' step onwards
    python3 build_all.py --skip equalise # leave out a step

hospitals_refined.csv is the single source of truth for hospital facts (level,
side, tags, phone, aliases). After editing it, run this script and commit the
result. Steps are listed in dependency order; the last two update the docs from
the data (sync_docs.py) and print what changed versus the last commit
(change_summary.py).
"""

import argparse
import glob
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HOSPITALS = "hospitals_refined.csv"
POSTCODES = "postcodes_master.csv"
POPULATION = "pcd_p001.csv"
BIRTHS = "birthsbypcdfinal.xlsx"
LOOKUP_ALL = "output/lookup/All_Postcodes.csv"
ANALYSIS_ALL = "output/analysis/All_Postcodes.csv"
EQUALISED_ALL = "output/All_Postcodes_Equalised.csv"
PROFILE_CODE = ["hospital_profiles.py"]

# name, script (+ args), inputs, outputs.  Paths are relative to the repo root;
# inputs/outputs only drive --changed and --list.
STEPS = [
    ("outcode-map", ["extract_outcode_json.py"],
     [HOSPITALS, "Outcode approach.html", "extract_outcode_json.py"],
     ["docs/outcode_map.json", "Outcode approach.html"]),
    ("lookup", ["postcode_lookup.py", "--profile", "lookup"],
     [HOSPITALS, POSTCODES, "postcode_lookup.py"] + PROFILE_CODE, [LOOKUP_ALL]),
    ("analysis", ["postcode_lookup.py", "--profile", "analysis"],
     [HOSPITALS, POSTCODES, "postcode_lookup.py"] + PROFILE_CODE, [ANALYSIS_ALL]),
    ("populations", ["calculate_catchment_populations.py"],
     [ANALYSIS_ALL, POPULATION, "calculate_catchment_populations.py"],
     ["docs/populations.json", "output/Hospital_Catchment_Populations.csv"]),
    ("births", ["calculate_catchment_births.py"],
     [ANALYSIS_ALL, BIRTHS, "calculate_catchment_births.py"],
     ["docs/births.json", "output/Hospital_Catchment_Births.csv"]),
    ("outcode-catchment", ["calculate_outcode_catchment.py"],
     ["docs/outcode_map.json", ANALYSIS_ALL, POPULATION, BIRTHS, "calculate_outcode_catchment.py"],
     ["docs/outcode_populations.json", "docs/outcode_births.json"]),
    ("equalise", ["equalise_catchments.py"],
     [ANALYSIS_ALL, POPULATION, HOSPITALS, "equalise_catchments.py"] + PROFILE_CODE,
     [EQUALISED_ALL, "output/Equalised_Summary.csv"]),
    ("comparison-page", ["build_comparison_page.py"],
     [ANALYSIS_ALL, EQUALISED_ALL, HOSPITALS, "build_comparison_page.py"],
     ["docs/comparison.html", "docs/comparison_dots.json"]),
    ("equalised-page", ["build_equalised_page.py"],
     [EQUALISED_ALL, HOSPITALS, "build_equalised_page.py"],
     ["docs/equalised_catchment.html", "docs/equalised_dots.json"]),
    ("static-site", ["build_static.py"],
     [LOOKUP_ALL, HOSPITALS, "build_static.py"],
     ["docs/postcodes.json", "docs/hospitals.json"]),
    ("catchment-map", ["generate_map.py"],
     [LOOKUP_ALL, HOSPITALS, "generate_map.py", "folium_utils.py"] + PROFILE_CODE,
     ["neonatal_catchment_map.html"]),
    ("extra-maps", ["generate_extra_maps.py"],
     [LOOKUP_ALL, HOSPITALS, "generate_extra_maps.py", "folium_utils.py"] + PROFILE_CODE,
     sorted(glob.glob(os.path.join(BASE_DIR, "docs/maps/map*.html"))) or ["docs/maps/map4_bubbles.html"]),
    ("docs", ["sync_docs.py"],
     [HOSPITALS, POSTCODES, LOOKUP_ALL, "docs/outcode_map.json", "docs/populations.json", "docs/births.json",
      "docs/outcode_populations.json", "docs/outcode_births.json", "sync_docs.py"],
     ["README.md", "TECHNICAL.md"]),
    # Report only: compares the fresh files with the last commit. Always runs, never fails the build.
    ("summary", ["change_summary.py"], [], []),
]


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _mtime(path):
    return os.path.getmtime(_abs(path)) if os.path.exists(_abs(path)) else None


def is_fresh(inputs, outputs):
    """True when every output exists and is newer than every input."""
    if not outputs:
        return False
    out_times = [_mtime(p) for p in outputs]
    if any(t is None for t in out_times):
        return False
    in_times = [t for t in (_mtime(p) for p in inputs) if t is not None]
    return not in_times or min(out_times) >= max(in_times)


def select_steps(args):
    names = [s[0] for s in STEPS]
    steps = list(STEPS)
    if args.from_step:
        if args.from_step not in names:
            sys.exit(f"Unknown step '{args.from_step}'. Steps: {', '.join(names)}")
        steps = steps[names.index(args.from_step):]
    if args.only:
        steps = [s for s in steps if any(o in s[0] for o in args.only)]
        if not steps:
            sys.exit(f"No step matches {args.only}. Steps: {', '.join(names)}")
    if args.skip:
        steps = [s for s in steps if not any(k in s[0] for k in args.skip)]
    return steps


def check_inputs():
    missing = [p for p in (HOSPITALS, POSTCODES, POPULATION, BIRTHS) if not os.path.exists(_abs(p))]
    if missing:
        sys.exit("Missing input files: " + ", ".join(missing))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list the steps and exit")
    ap.add_argument("--changed", action="store_true", help="skip steps whose outputs are newer than their inputs")
    ap.add_argument("--only", nargs="+", metavar="NAME", help="run only steps whose name contains one of these")
    ap.add_argument("--skip", nargs="+", metavar="NAME", help="skip steps whose name contains one of these")
    ap.add_argument("--from", dest="from_step", metavar="NAME", help="start at this step")
    args = ap.parse_args()

    steps = select_steps(args)
    if args.list:
        for name, cmd, inputs, outputs in STEPS:
            mark = " " if name in [s[0] for s in steps] else "-"
            print(f"{mark} {name:<18} {' '.join(cmd)}")
            print(f"    in : {', '.join(inputs)}")
            print(f"    out: {', '.join(os.path.relpath(_abs(o), BASE_DIR) for o in outputs)}")
        return

    check_inputs()
    started = time.time()
    for name, cmd, inputs, outputs in steps:
        if args.changed and is_fresh(inputs, outputs):
            print(f"-- {name}: up to date, skipping")
            continue
        print(f"\n== {name}: python3 {' '.join(cmd)}", flush=True)
        t0 = time.time()
        rc = subprocess.call([sys.executable, "-u"] + cmd, cwd=BASE_DIR)
        if rc != 0 and name == "summary":
            print("   (change summary failed; the build itself is fine)")
        elif rc != 0:
            sys.exit(f"\nStep '{name}' failed (exit {rc}). Fix it, then resume with: "
                     f"python3 build_all.py --from {name}")
        print(f"   {name} done in {time.time() - t0:.1f}s")
    print(f"\nAll steps finished in {time.time() - started:.0f}s. "
          "Review with `git status` / `git diff --stat`, then commit.")


if __name__ == "__main__":
    main()
