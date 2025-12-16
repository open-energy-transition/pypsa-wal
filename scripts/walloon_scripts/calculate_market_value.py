# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

"""
Compute market value metrics for generators and demand-side sobriety.

Outputs
-------
- market_value_by_generator.csv : Market value, revenue, and energy by generator
- demand_reduction_value_ts.csv : Marginal price (value of 1 MWh demand reduction)
  for the electricity demand buses over all snapshots
Generator-level market value factors are included in the generator CSV.
"""

import logging
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config
from scripts.walloon_scripts.calculate_prices import (
    _compute_electric_loads_and_prices,
    get_electriciy_price_weighted,
)

logger = logging.getLogger(__name__)


def market_value_by_generator(n: pypsa.Network, system_price: float) -> pd.DataFrame:
    """
    Compute market value per generator (positive dispatch only).
    Returns DataFrame with generator, bus, carrier, energy, revenue, market value, and MVF.
    """
    weights = n.snapshot_weightings.generators
    gen_index = n.generators.index
    gen_bus = n.generators.bus

    # dispatch of generators
    dispatch = n.generators_t.p.reindex(columns=gen_index).multiply(weights, axis=0)
    if dispatch.isna().any().any():
        logger.warning(
            "Dispatch contains NaNs; market value results may be incomplete."
        )
    # prices at buses
    bus_prices = n.buses_t.marginal_price
    # align bus prices to generator buses and relabel columns by generator id
    price_at_gen = bus_prices.reindex(columns=gen_bus).set_axis(gen_index, axis=1)
    if price_at_gen.isna().any().any():
        logger.warning(
            "Price matrix contains NaNs; market value results may be incomplete."
        )

    # calculate revenue and sum across snapshots
    revenue = (price_at_gen * dispatch).sum()

    # calculate energy by summing dispatch across snapshots
    energy = dispatch.sum()

    # create market value DataFrame
    df = (
        pd.DataFrame(
            {
                "generator": energy.index,
                "bus": n.generators.bus.values,
                "carrier": n.generators.carrier.values,
                "energy_MWh_per_year": energy.values,
                "revenue_EUR_per_year": revenue.values,
            }
        )
        .query("energy_MWh_per_year > 0")
        .assign(
            market_value_EUR_per_MWh=lambda d: d.revenue_EUR_per_year
            / d.energy_MWh_per_year,
            market_value_factor=lambda d: d.market_value_EUR_per_MWh / system_price
            if system_price > 0
            else pd.NA,
        )
    )
    return df


def demand_reduction_value_ts(n: pypsa.Network) -> pd.DataFrame:
    """
    Marginal price time series for demand buses (value of 1 MWh reduction).
    No additional weighting is applied: price already expresses EUR/MWh at (bus, snapshot).
    """
    prices, total_loads = _compute_electric_loads_and_prices(n)
    return prices[total_loads.columns]


def main(network_path: Path, output_paths: Iterable[Path]) -> None:
    n = pypsa.Network(network_path)
    output_paths = list(output_paths)
    if len(output_paths) != 2:
        raise ValueError("Expected two output paths.")
    system_price, _ = get_electriciy_price_weighted(n)
    gen_mv = market_value_by_generator(n, system_price)
    demand_value_ts = demand_reduction_value_ts(n)
    gen_mv.to_csv(output_paths[0], index=False)
    demand_value_ts.to_csv(output_paths[1])


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "calculate_market_value",
            clusters="adm",
            opts="",
            sector_opts="",
            planning_horizons="2025",
            run="walloon-model",
        )
    configure_logging(snakemake)
    set_scenario_config(snakemake)
    output_files = [
        Path(snakemake.output.market_value_by_generator),
        Path(snakemake.output.demand_reduction_value_ts),
    ]
    Path(output_files[0]).parent.mkdir(parents=True, exist_ok=True)
    main(Path(snakemake.input.network), output_files)
