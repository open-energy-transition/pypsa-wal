"""Convert Walloon existing capacities into PyPSA-compatible custom powerplant data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

TECH_MAP: dict[str, str] = {
    "CCGT": "CCGT",
    "OCGT": "OCGT",
    "Steam Turbine": "Steam Turbine",
    "Wind Turbine": "Onshore Wind",
    "Run Of River": "Run-Of-River",
    "Run-Of-River": "Run-Of-River",
    "Run-of-river": "Run-Of-River",
    "Photovoltaic": "Solar",
    "Solar": "Solar",
    "Reservoir": "Reservoir",
    "Pumped Storage": "Pumped Storage",
    "Engine": "Engine",
}

FUEL_MAP: dict[str, str] = {
    "Natural Gas": "Natural Gas",
    "Nuclear": "Nuclear",
    "Oil": "Oil",
    "Wind": "Onshore Wind",
    "Biogas": "Biogas",
    "Waste": "Waste",
    "Hydro": "Hydro",
    "Sun": "Solar",
    "Pellets": "Solid Biomass",
    "Biomass": "Solid Biomass",
}


def infer_bus(nuts_code: str | float) -> str:
    if isinstance(nuts_code, str):
        code = nuts_code.strip().upper()
        if code.startswith("BE1"):
            return "BEBRU"
        if code.startswith("BE2"):
            return "BEVLG"
        if code.startswith("BE3"):
            return "BEWAL"
    return "BEWAL"


def make_name(row: pd.Series, idx: int) -> str:
    label = row.get("NomInstallation")
    if isinstance(label, str) and label.strip():
        return label.strip()
    technology = row.get("Technology") or "Plant"
    code = row.get("NUTS3_code") or "UNKNOWN"
    return f"{technology}_{code}_{idx}"


def main(input_path: Path, output_path: Path) -> None:
    df = pd.read_csv(input_path, encoding="utf-8-sig")

    df["Name"] = [make_name(r, i) for i, r in df.iterrows()]
    df["Fueltype"] = (
        df["Fueltype"].astype(str).str.strip().replace(FUEL_MAP)
    )
    df["Technology"] = (
        df["Technology"].astype(str).str.strip().replace(TECH_MAP)
    )
    df = df[~df["Fueltype"].isin(["Onshore Wind", "Solar"])]
    df["Set"] = "PP"
    df["Country"] = df["NUTS3_code"].fillna("BE").str[:2].str.upper()
    df["Capacity"] = df["Capacity"].astype(float)
    df["Efficiency"] = pd.to_numeric(df["Efficiency"], errors="coerce")
    df["DateIn"] = pd.to_numeric(df["DateIn"], errors="coerce")
    df["Lifetime"] = pd.to_numeric(df["Lifetime"], errors="coerce")
    df["DateOut"] = df["DateIn"] + df["Lifetime"]
    df["bus"] = df["NUTS3_code"].apply(infer_bus)

    converted = pd.DataFrame(
        {
            "Name": df["Name"],
            "Fueltype": df["Fueltype"],
            "Technology": df["Technology"],
            "Set": df["Set"],
            "Country": df["Country"],
            "Capacity": df["Capacity"],
            "Efficiency": df["Efficiency"],
            "DateIn": df["DateIn"],
            "DateRetrofit": pd.NA,
            "DateOut": df["DateOut"],
            "lat": 50.5334,
            "lon": 5.2714,
            "Duration": pd.NA,
            "Volume_Mm3": pd.NA,
            "DamHeight_m": pd.NA,
            "StorageCapacity_MWh": pd.NA,
            "EIC": pd.NA,
            "projectID": pd.NA,
            "bus": df["bus"],
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    converted.to_csv(output_path, index=False)
    print(f"Wrote {len(converted)} rows to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/walloon/wal_2021_existing_capacities_2.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/walloon/wal_existing_capacities_converted.csv"),
    )
    args = parser.parse_args()
    main(args.input, args.output)
