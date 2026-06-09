"""Helpers for loading hospitals by usage profile (lookup vs analysis)."""

import pandas as pd

PROFILE_COLUMN = {
    "lookup": "include_lookup",
    "analysis": "include_analysis",
}

_TRUE_VALUES = {"1", "true", "t", "yes", "y"}


def _to_bool(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() in _TRUE_VALUES


def load_hospitals_for_profile(csv_path="hospitals_refined.csv", profile="lookup"):
    """Load hospitals and filter by profile flags when those columns exist."""
    if profile not in PROFILE_COLUMN:
        raise ValueError(f"Unknown profile '{profile}'. Expected one of: {', '.join(PROFILE_COLUMN)}")

    hospitals = pd.read_csv(csv_path)
    hospitals.columns = hospitals.columns.str.strip()

    if "Hospital Name" in hospitals.columns:
        hospitals["Hospital Name"] = hospitals["Hospital Name"].str.strip()

    profile_col = PROFILE_COLUMN[profile]

    if profile_col in hospitals.columns:
        mask = hospitals[profile_col].apply(_to_bool)
        return hospitals[mask].copy()

    # Backward-compatible fallback: if profile columns are missing, include all rows.
    return hospitals.copy()
