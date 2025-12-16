import logging
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config
from scripts.walloon_scripts.calculate_prices import get_electriciy_price_weighted

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
    # prices at buses
    bus_prices = n.buses_t.marginal_price
    # align bus prices to generator buses and relabel columns by generator id
    price_at_gen = bus_prices.reindex(columns=gen_bus).set_axis(gen_index, axis=1)
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


def main(network_path: Path, output_paths: Iterable[Path]) -> None:
    n = pypsa.Network(network_path)
    output_paths = list(output_paths)
    if len(output_paths) != 1:
        raise ValueError("Expected one output path.")
    system_price, _ = get_electriciy_price_weighted(n)
    gen_mv = market_value_by_generator(n, system_price)
    gen_mv.to_csv(output_paths[0], index=False)


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
    output_files = [Path(snakemake.output.market_value_by_generator)]
    Path(output_files[0]).parent.mkdir(parents=True, exist_ok=True)
    main(Path(snakemake.input.network), output_files)
