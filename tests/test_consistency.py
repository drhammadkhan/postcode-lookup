"""
Consistency checks between hospitals_refined.csv (the source of truth) and every
file generated from it.  If one of these fails after you edit the CSV, run

    python3 build_all.py

and commit the regenerated files.
"""

import json
import os
import re
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    return os.path.join(ROOT, *parts)


def load_json(*parts):
    with open(path(*parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(path(*parts), encoding="utf-8") as f:
        return f.read()


REBUILD = "Generated files are out of date - run `python3 build_all.py` and commit the result."


@pytest.fixture(scope="session")
def hospitals():
    df = pd.read_csv(path("hospitals_refined.csv"))
    df.columns = df.columns.str.strip()
    df["Hospital Name"] = df["Hospital Name"].str.strip()
    return df


@pytest.fixture(scope="session")
def lookup_hospitals(hospitals):
    return hospitals[hospitals["include_lookup"] == 1]


@pytest.fixture(scope="session")
def analysis_hospitals(hospitals):
    return hospitals[hospitals["include_analysis"] == 1]


@pytest.fixture(scope="session")
def level_of(hospitals):
    return dict(zip(hospitals["Hospital Name"], hospitals["Level"].astype(int)))


@pytest.fixture(scope="session")
def lookup_all():
    return pd.read_csv(path("output", "lookup", "All_Postcodes.csv"), dtype={"Postcode": str})


@pytest.fixture(scope="session")
def analysis_all():
    return pd.read_csv(path("output", "analysis", "All_Postcodes.csv"), dtype={"Postcode": str})


# ── 1. The source CSV itself ──────────────────────────────────────────────────

def test_csv_has_required_columns(hospitals):
    needed = {"Hospital Name", "Level", "Sector", "Specialty Tags", "Postcode", "Latitude", "Longitude",
              "Side", "include_lookup", "include_analysis", "Phone", "Aliases"}
    assert needed <= set(hospitals.columns)


def test_csv_values_are_valid(hospitals):
    assert hospitals["Hospital Name"].is_unique
    assert set(hospitals["Level"]) <= {1, 2, 3}
    assert set(hospitals["Side"]) <= {"North", "South", "Both"}
    assert set(hospitals["include_lookup"]) <= {0, 1}
    assert set(hospitals["include_analysis"]) <= {0, 1}
    assert hospitals["Phone"].notna().all(), "every hospital needs a Phone"
    assert hospitals["Latitude"].between(51.0, 52.0).all()
    assert hospitals["Longitude"].between(-1.0, 0.5).all()


def test_aliases_are_unique_across_hospitals(hospitals):
    seen = {}
    for _, row in hospitals.iterrows():
        names = [row["Hospital Name"]] + ([] if pd.isna(row["Aliases"]) else str(row["Aliases"]).split(";"))
        for n in names:
            n = n.strip()
            assert seen.setdefault(n, row["Hospital Name"]) == row["Hospital Name"], f"alias '{n}' reused"


def test_analysis_hospitals_are_in_lookup(hospitals):
    assert not hospitals[(hospitals["include_analysis"] == 1) & (hospitals["include_lookup"] == 0)].shape[0]


# ── 2. Site data (docs/hospitals.json) ────────────────────────────────────────

def test_hospitals_json_matches_csv(lookup_hospitals):
    site = {h["name"]: h for h in load_json("docs", "hospitals.json")}
    assert set(site) == set(lookup_hospitals["Hospital Name"]), REBUILD
    for _, row in lookup_hospitals.iterrows():
        h = site[row["Hospital Name"]]
        assert h["level"] == row["Level"], f"{row['Hospital Name']} level. {REBUILD}"
        assert h["side"] == row["Side"], f"{row['Hospital Name']} side. {REBUILD}"
        assert h["phone"] == row["Phone"], f"{row['Hospital Name']} phone. {REBUILD}"
        assert h["tags"] == str(row["Specialty Tags"]).strip(), f"{row['Hospital Name']} tags. {REBUILD}"
        assert (h["lat"], h["lon"]) == (round(row["Latitude"], 4), round(row["Longitude"], 4))


def test_site_pages_have_no_hardcoded_phone_numbers():
    for page in ("docs/index.html", "docs/hospitals.html"):
        assert not re.search(r"'\d{3,5} \d{3,4} ?\d{3,4}'", read(*page.split("/"))), \
            f"{page} hardcodes phone numbers; they belong in hospitals_refined.csv"


# ── 3. Postcode assignment files ──────────────────────────────────────────────

@pytest.mark.parametrize("profile", ["lookup", "analysis"])
def test_assignments_respect_levels_and_profile(profile, hospitals, level_of, lookup_all, analysis_all):
    df = lookup_all if profile == "lookup" else analysis_all
    allowed = hospitals[hospitals[f"include_{profile}"] == 1]["Hospital Name"]
    for col in ("Closest_Any", "Closest_L1", "Closest_L2", "Closest_L3"):
        names = set(df[col].dropna()) - {"None Found"}
        assert names <= set(allowed), f"{profile} {col}: hospital not in profile. {REBUILD}"
    for lvl in (1, 2, 3):
        names = set(df[f"Closest_L{lvl}"].dropna()) - {"None Found"}
        wrong = {n for n in names if level_of[n] != lvl}
        assert not wrong, f"{profile}: Closest_L{lvl} contains {wrong} which are not level {lvl}. {REBUILD}"


@pytest.mark.parametrize("profile", ["lookup", "analysis"])
def test_nearest_any_is_not_further_than_nearest_at_a_level(profile, lookup_all, analysis_all):
    df = lookup_all if profile == "lookup" else analysis_all
    for lvl in (1, 2, 3):
        sub = df[df[f"Closest_L{lvl}"] != "None Found"]
        # Nearest-neighbour search uses scaled Euclidean distance, so a near-tie can be
        # resolved ~10 m the "wrong" way when compared with haversine; allow 50 m.
        assert (sub["Distance_Any_km"] <= sub[f"Distance_L{lvl}_km"] + 0.05).all()


def test_equalised_file_carries_current_assignments(analysis_all):
    eq = pd.read_csv(path("output", "All_Postcodes_Equalised.csv"), dtype={"Postcode": str})
    base = analysis_all.set_index("Postcode")
    eq = eq.set_index("Postcode")
    assert set(eq.index) == set(base.index), REBUILD
    for col in ("Closest_Any", "Closest_L1", "Closest_L2", "Closest_L3"):
        assert (eq[col].fillna("") == base.loc[eq.index, col].fillna("")).all(), f"equalised {col} stale. {REBUILD}"


# ── 4. Catchment totals ───────────────────────────────────────────────────────

def test_populations_and_births_match_assignments(analysis_all, level_of):
    pops = {r["hospital"]: r for r in load_json("docs", "populations.json")}
    births = {r["hospital"]: r for r in load_json("docs", "births.json")}
    for lvl in (1, 2, 3):
        for table, field in ((pops, "population"), (births, "births")):
            owners = {h for h, r in table.items() if r[f"l{lvl}_{field}"] > 0 and h != "None Found"}
            wrong = {h for h in owners if level_of[h] != lvl}
            assert not wrong, f"l{lvl}_{field} is non-zero for {wrong}, which are not level {lvl}. {REBUILD}"
    assigned = set(analysis_all["Closest_Any"].dropna())
    assert {h for h, r in pops.items() if r["any_population"] > 0} <= assigned


# ── 5. Outcode routing ────────────────────────────────────────────────────────

def test_outcode_map_uses_known_hospitals(hospitals):
    # The routing guide may name lookup-only hospitals (e.g. Epsom), so check against every row.
    used = {h for hs in load_json("docs", "outcode_map.json")["outward_to_hospitals"].values() for h in hs}
    assert used <= set(hospitals["Hospital Name"])


def test_outcode_guide_levels_match_csv(hospitals, level_of):
    html = read("Outcode approach.html")
    alias_to_name = {}
    for _, row in hospitals.iterrows():
        for a in ([] if pd.isna(row["Aliases"]) else str(row["Aliases"]).split(";")) + [row["Hospital Name"]]:
            alias_to_name[a.strip()] = row["Hospital Name"]
    checked = 0
    for m in re.finditer(r'name:\s*"([^"]+)",\s*aliases:\s*\[(.*?)\].*?level:\s*(\d)', html, re.DOTALL):
        names = {alias_to_name[a] for a in re.findall(r'"([^"]+)"', m.group(2)) if a in alias_to_name}
        if len(names) == 1:
            checked += 1
            assert level_of[names.pop()] == int(m.group(3)), f"{m.group(1)} level differs. {REBUILD}"
    assert checked >= 20


# ── 6. Maps and pages that embed hospital levels ──────────────────────────────

def test_map_popups_show_csv_levels(lookup_hospitals, level_of):
    for rel in ("neonatal_catchment_map.html", "docs/maps/map4_bubbles.html"):
        text = read(*rel.split("/"))
        for name, lvl in level_of.items():
            if name not in set(lookup_hospitals["Hospital Name"]):
                continue
            for m in re.finditer(re.escape(name.replace("&", "&amp;")) + r"</b><br>Level (\d)", text):
                assert int(m.group(1)) == lvl, f"{rel}: {name} shows level {m.group(1)}. {REBUILD}"


@pytest.mark.parametrize("rel", ["docs/comparison.html", "docs/equalised_catchment.html"])
def test_catchment_pages_show_csv_levels(rel, level_of):
    text = read(*rel.split("/"))
    found = re.findall(r'"name":"([^"]+)","(?:lat":[^,]+,"lon":[^,]+,"level|level)":(\d)', text)
    assert found, "no hospitals found in page"
    for name, lvl in found:
        assert level_of[name] == int(lvl), f"{rel}: {name}. {REBUILD}"


# ── 7. README / TECHNICAL stay in step with the data ──────────────────────────

def test_docs_are_in_sync():
    result = subprocess.run([sys.executable, path("sync_docs.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
