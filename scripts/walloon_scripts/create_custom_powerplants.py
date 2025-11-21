"""Convert Walloon existing capacities into PyPSA-compatible custom powerplant data."""


from scripts._helpers import configure_logging, set_scenario_config

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


def build_BE_powerplants(wal_existing, custom_powerplants) -> None:
    df = pd.read_csv(wal_existing, encoding="utf-8-sig")

    df["Name"] = [make_name(r, i) for i, r in df.iterrows()]
    df["Fueltype"] = df["Fueltype"].astype(str).str.strip().replace(FUEL_MAP)
    df["Technology"] = df["Technology"].astype(str).str.strip().replace(TECH_MAP)
    df["Set"] = "PP"
    df["Country"] = df["NUTS3_code"].fillna("BE").str[:2].str.upper()
    df["Capacity"] = df["Capacity"].astype(float)
    df["Efficiency"] = pd.to_numeric(df["Efficiency"], errors="coerce")
    df["DateIn"] = pd.to_numeric(df["DateIn"], errors="coerce")
    df["Lifetime"] = pd.to_numeric(df["Lifetime"], errors="coerce")
    df["DateOut"] = df["DateIn"] + df["Lifetime"]
    df["bus"] = df["NUTS3_code"].apply(infer_bus)

    mask_custom = ~df["Fueltype"].isin(["Onshore Wind", "Solar"]) & (
        df["DateIn"] < 2025
    )
    custom = pd.DataFrame(
        {
            "Name": df.loc[mask_custom, "Name"],
            "Fueltype": df.loc[mask_custom, "Fueltype"],
            "Technology": df.loc[mask_custom, "Technology"],
            "Set": df.loc[mask_custom, "Set"],
            "Country": df.loc[mask_custom, "Country"],
            "Capacity": df.loc[mask_custom, "Capacity"],
            "Efficiency": df.loc[mask_custom, "Efficiency"],
            "DateIn": df.loc[mask_custom, "DateIn"],
            "DateRetrofit": pd.NA,
            "DateOut": df.loc[mask_custom, "DateOut"],
            "lat": 50.5334,
            "lon": 5.2714,
            "Duration": pd.NA,
            "Volume_Mm3": pd.NA,
            "DamHeight_m": pd.NA,
            "StorageCapacity_MWh": pd.NA,
            "EIC": pd.NA,
            "projectID": pd.NA,
            "bus": df.loc[mask_custom, "bus"],
        }
    )
    custom_add = pd.read_csv(custom_powerplants)
    custom = pd.concat([custom, custom_add], ignore_index=True)
    custom = custom[~custom["Fueltype"].isin(["Onshore Wind", "Solar"])]

    potential = df.loc[~mask_custom, ["bus", "Fueltype", "Capacity"]]
    pivot = (
        potential.groupby(["Fueltype", "bus"])["Capacity"]
        .sum()
        .unstack(level=0)
        .fillna(0.0)
    )
    pivot.columns = pivot.columns.str.lower()
    pivot.rename(columns={"onshore wind": "onwind", "solar": "solar-all"}, inplace=True)

    return custom, pivot


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_powerplants")
    configure_logging(snakemake)
    set_scenario_config(snakemake)

    custom_powerplants, agg_p_nom_minmax = build_BE_powerplants(
        snakemake.input.wal_capacities,
        snakemake.input.custom_powerplants
    )

    custom_powerplants.to_csv(snakemake.output.custom_powerplants, index=False)
