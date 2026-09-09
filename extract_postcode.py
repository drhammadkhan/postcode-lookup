import argparse
from pathlib import Path

import numpy as np
import pandas as pd


LONDON_REGION_CODE = "E12000007"
USECOLS = ["pcds", "rgn25cd", "lat", "long"]
OUTPUT_COLUMNS = ["Postcode", "Latitude", "Longitude"]
HOSPITAL_USECOLS = ["Hospital Name", "Postcode", "Latitude", "Longitude", "include_lookup"]
TRUE_VALUES = {"1", "true", "t", "yes", "y"}


def normalise_postcode(value: str) -> str:
    return str(value).replace(" ", "").upper()


def normalise_output_rows(rows: pd.DataFrame) -> pd.DataFrame:
    output_rows = rows.rename(
        columns={
            "pcds": "Postcode",
            "lat": "Latitude",
            "long": "Longitude",
        }
    )
    output_rows = output_rows[OUTPUT_COLUMNS].copy()
    output_rows["Postcode"] = output_rows["Postcode"].map(normalise_postcode)
    output_rows["Latitude"] = pd.to_numeric(output_rows["Latitude"], errors="coerce")
    output_rows["Longitude"] = pd.to_numeric(output_rows["Longitude"], errors="coerce")
    return output_rows.dropna(subset=["Latitude", "Longitude"])


def extract_london_postcodes(input_csv: Path, output_csv: Path, chunk_size: int) -> int:
    """Extract London postcodes from ONSPD into the project master CSV shape."""
    total_rows = 0
    wrote_header = False

    for chunk in pd.read_csv(
        input_csv,
        usecols=USECOLS,
        chunksize=chunk_size,
        dtype=str,
        low_memory=False,
    ):
        london_rows = chunk.loc[chunk["rgn25cd"] == LONDON_REGION_CODE, ["pcds", "lat", "long"]]

        if london_rows.empty:
            continue

        output_rows = normalise_output_rows(london_rows)

        output_rows.to_csv(
            output_csv,
            mode="a" if wrote_header else "w",
            index=False,
            header=not wrote_header,
        )

        wrote_header = True
        total_rows += len(output_rows)

    return total_rows


def load_lookup_hospitals(hospitals_csv: Path) -> pd.DataFrame:
    hospitals = pd.read_csv(hospitals_csv, usecols=lambda col: col in HOSPITAL_USECOLS)
    hospitals.columns = hospitals.columns.str.strip()
    if "include_lookup" in hospitals.columns:
        include = hospitals["include_lookup"].apply(
            lambda value: str(value).strip().lower() in TRUE_VALUES if pd.notna(value) else False
        )
        hospitals = hospitals[include].copy()
    hospitals["Latitude"] = pd.to_numeric(hospitals["Latitude"], errors="coerce")
    hospitals["Longitude"] = pd.to_numeric(hospitals["Longitude"], errors="coerce")
    hospitals = hospitals.dropna(subset=["Latitude", "Longitude"])
    if hospitals.empty:
        raise ValueError(f"No usable hospital coordinates found in {hospitals_csv}")
    return hospitals


def haversine_min_km(
    post_lat: np.ndarray,
    post_lon: np.ndarray,
    hospital_lat: np.ndarray,
    hospital_lon: np.ndarray,
) -> np.ndarray:
    """Return each postcode's nearest hospital distance in km."""
    radius_km = 6371.0
    post_lat_rad = np.radians(post_lat)[:, None]
    post_lon_rad = np.radians(post_lon)[:, None]
    hosp_lat_rad = np.radians(hospital_lat)[None, :]
    hosp_lon_rad = np.radians(hospital_lon)[None, :]

    dlat = hosp_lat_rad - post_lat_rad
    dlon = hosp_lon_rad - post_lon_rad
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(post_lat_rad) * np.cos(hosp_lat_rad) * np.sin(dlon / 2) ** 2
    )
    return (radius_km * 2 * np.arcsin(np.sqrt(a))).min(axis=1)


def extract_hospital_buffer_postcodes(
    input_csv: Path,
    output_csv: Path,
    hospitals_csv: Path,
    buffer_km: float,
    chunk_size: int,
) -> int:
    """Extract national postcodes within a distance buffer of any lookup hospital."""
    hospitals = load_lookup_hospitals(hospitals_csv)
    hospital_lat = hospitals["Latitude"].to_numpy(dtype=float)
    hospital_lon = hospitals["Longitude"].to_numpy(dtype=float)
    lat_padding = buffer_km / 111.0
    lon_padding = buffer_km / (111.0 * np.cos(np.radians(hospital_lat.mean())))
    min_lat = hospital_lat.min() - lat_padding
    max_lat = hospital_lat.max() + lat_padding
    min_lon = hospital_lon.min() - lon_padding
    max_lon = hospital_lon.max() + lon_padding

    total_rows = 0
    wrote_header = False

    for chunk in pd.read_csv(
        input_csv,
        usecols=["pcds", "lat", "long"],
        chunksize=chunk_size,
        dtype=str,
        low_memory=False,
    ):
        rows = normalise_output_rows(chunk)
        if rows.empty:
            continue

        bbox_rows = rows[
            rows["Latitude"].between(min_lat, max_lat)
            & rows["Longitude"].between(min_lon, max_lon)
        ].copy()
        if bbox_rows.empty:
            continue

        nearest_km = haversine_min_km(
            bbox_rows["Latitude"].to_numpy(dtype=float),
            bbox_rows["Longitude"].to_numpy(dtype=float),
            hospital_lat,
            hospital_lon,
        )
        output_rows = bbox_rows[nearest_km <= buffer_km]
        if output_rows.empty:
            continue

        output_rows.to_csv(
            output_csv,
            mode="a" if wrote_header else "w",
            index=False,
            header=not wrote_header,
        )

        wrote_header = True
        total_rows += len(output_rows)

    return total_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract postcodes from the ONS Postcode Directory.")
    parser.add_argument(
        "--mode",
        choices=["london-region", "hospital-buffer"],
        default="london-region",
        help="Extraction strategy.",
    )
    parser.add_argument(
        "--input",
        default="ONSPD_MAY_2026_UK.csv",
        type=Path,
        help="Path to the full ONSPD CSV.",
    )
    parser.add_argument(
        "--output",
        default="postcodes_master_new.csv",
        type=Path,
        help="Output CSV path.",
    )
    parser.add_argument(
        "--hospitals-csv",
        default="hospitals_refined.csv",
        type=Path,
        help="Hospital CSV used by --mode hospital-buffer.",
    )
    parser.add_argument(
        "--buffer-km",
        default=50.0,
        type=float,
        help="Include postcodes within this distance of any lookup hospital.",
    )
    parser.add_argument(
        "--chunk-size",
        default=100_000,
        type=int,
        help="Number of rows to process per chunk.",
    )
    args = parser.parse_args()

    if args.output.exists():
        args.output.unlink()

    if args.mode == "hospital-buffer":
        total_rows = extract_hospital_buffer_postcodes(
            args.input,
            args.output,
            args.hospitals_csv,
            args.buffer_km,
            args.chunk_size,
        )
    else:
        total_rows = extract_london_postcodes(args.input, args.output, args.chunk_size)

    if total_rows:
        print(f"Saved {total_rows:,} postcodes to {args.output}")
    else:
        print("No postcodes found")


if __name__ == "__main__":
    main()
