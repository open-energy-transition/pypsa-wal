import logging
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)

# Carriers that should be treated as renewables when building the high-level
# categories. Extend if new renewable carriers are introduced.
RES_CARRIERS = {
    "onwind",
    "offwind-ac",
    "offwind-dc",
    "offwind-float",
    "solar",
    "solar-hsat",
    "solar rooftop",
    "ror",
    "run of river",
    "hydro",
    "hydro reservoir",
    "biogas",
    "solid biomass",
}


def _series_to_df(series: pd.Series, value_name: str) -> pd.DataFrame:
    """Reset index on a cost series to a tidy DataFrame."""
    df = series.reset_index()
    df.columns = list(df.columns[:-1]) + [value_name]
    return df


def capex_opex_by_bus_carrier(n: pypsa.Network) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute detailed CAPEX and OPEX grouped by component, bus, and carrier.
    """
    capex = n.statistics.capex(groupby=["bus", "carrier"])
    opex = n.statistics.opex(groupby=["bus", "carrier"])
    capex_df = _series_to_df(capex, "capex_eur_per_year")
    opex_df = _series_to_df(opex, "opex_eur_per_year")
    return capex_df, opex_df


def lcoe_by_carrier(n: pypsa.Network) -> pd.DataFrame:
    """
    Compute LCOE per carrier using PyPSA statistics.

    CAPEX and OPEX are annualised values from statistics; supply is the annual
    delivered energy. LCOE = (CAPEX + OPEX) / supply.
    """
    capex = n.statistics.capex(groupby="carrier").groupby(level="carrier").sum()
    opex = n.statistics.opex(groupby="carrier").groupby(level="carrier").sum()
    supply = (
        n.statistics.energy_balance(
            bus_carrier="AC",
            groupby="carrier",
            groupby_time="sum",
            aggregate_across_components=True,
        )
        .groupby(level="carrier")
        .sum()
    )

    df = pd.DataFrame(
        {
            "capex_eur_per_year": capex,
            "opex_eur_per_year": opex,
            "supply_MWh_per_year": supply,
        }
    )
    df = df[df["supply_MWh_per_year"] != 0]
    df["lcoe_EUR_per_MWh"] = (df["capex_eur_per_year"] + df["opex_eur_per_year"]) / df[
        "supply_MWh_per_year"
    ]
    df.index.name = "carrier"
    return df.reset_index()


def _categorise_main_tech(carrier: str) -> str | None:
    """Map carriers into the requested high-level buckets."""
    name = carrier.lower()
    # Keep renewables disaggregated: do not bucket RES together.
    if "nuclear" in name or carrier in {"uranium"}:
        return "nuclear"
    if "ccgt" in name and "cc" in name:
        return "CCGT+CCS"
    if "ccgt" in name:
        return "CCGT"
    if "h2" in name or "hydrogen" in name:
        return "H2"
    return None


def aggregate_main_categories(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-carrier LCOE table into an overall total across all carriers.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "category",
                "capex_eur_per_year",
                "opex_eur_per_year",
                "supply_MWh_per_year",
                "lcoe_EUR_per_MWh",
            ]
        )

    totals = df[
        ["capex_eur_per_year", "opex_eur_per_year", "supply_MWh_per_year"]
    ].sum()
    lcoe_total = (totals["capex_eur_per_year"] + totals["opex_eur_per_year"]) / totals[
        "supply_MWh_per_year"
    ]
    return pd.DataFrame(
        [
            {
                "category": "all_carriers",
                "capex_eur_per_year": totals["capex_eur_per_year"],
                "opex_eur_per_year": totals["opex_eur_per_year"],
                "supply_MWh_per_year": totals["supply_MWh_per_year"],
                "lcoe_EUR_per_MWh": lcoe_total,
            }
        ]
    )


def main(network_path: Path, output_paths: Iterable[Path]) -> None:
    n = pypsa.Network(network_path)
    capex_df, opex_df = capex_opex_by_bus_carrier(n)
    lcoe_df = lcoe_by_carrier(n)

    output_paths = list(output_paths)
    if len(output_paths) != 3:
        raise ValueError("Expected three output paths (capex, opex, lcoe).")

    capex_df.to_csv(output_paths[0], index=False)
    opex_df.to_csv(output_paths[1], index=False)
    lcoe_df.to_csv(output_paths[2], index=False)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "calculate_costs",
            clusters="adm",
            opts="",
            sector_opts="",
            planning_horizons="2025",
            run="walloon-model",
        )
    configure_logging(snakemake)
    set_scenario_config(snakemake)
    output_files = [
        Path(snakemake.output.capex),
        Path(snakemake.output.opex),
        Path(snakemake.output.lcoe),
    ]
    Path(output_files[0]).parent.mkdir(parents=True, exist_ok=True)
    main(Path(snakemake.input.network), output_files)
