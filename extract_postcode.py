import argparse
from pathlib import Path

import pandas as pd


LONDON_REGION_CODE = "E12000007"
USECOLS = ["pcds", "rgn25cd", "lat", "long"]
OUTPUT_COLUMNS = ["Postcode", "Latitude", "Longitude"]


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

        output_rows = london_rows.rename(
            columns={
                "pcds": "Postcode",
                "lat": "Latitude",
                "long": "Longitude",
            }
        )
        output_rows = output_rows[OUTPUT_COLUMNS]
        output_rows["Postcode"] = output_rows["Postcode"].str.replace(" ", "", regex=False).str.upper()

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
    parser = argparse.ArgumentParser(
        description="Extract London postcodes from the ONS Postcode Directory."
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
        "--chunk-size",
        default=100_000,
        type=int,
        help="Number of rows to process per chunk.",
    )
    args = parser.parse_args()

    total_rows = extract_london_postcodes(args.input, args.output, args.chunk_size)

    if total_rows:
        print(f"Saved {total_rows:,} London postcodes to {args.output}")
    else:
        print(f"No postcodes found for region {LONDON_REGION_CODE}")


if __name__ == "__main__":
    main()
