import logging
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def market_value_by_generator(n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate market value and market value factor of generators.

    Market value is calculated using n.statistics.market_value for Generators and
    Links connected to AC or low-voltage buses. The market value factor is the ratio
    of market value to average market price at the bus where the generator or link
    is connected. Average price is defined as the weighted average of the
    marginal prices at the generators' bus, weighted by the system load.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - name: Name of the generator or link.
        - component: 'Generator' or 'Link'.
        - bus: The bus the component is connected to.
        - carrier: The carrier of the component.
        - market_value_EUR_per_MWh: The market value in EUR/MWh.
        - average_price_EUR_per_MWh: The average market price at the bus in EUR/MWh.
        - market_value_factor: The ratio of market value to average price.
    """
    weights = n.snapshot_weightings.generators
    price_ts = n.buses_t.marginal_price
    weighted_load = n.loads_t.p_set.sum(axis=1) * weights
    total_load = weighted_load.sum()

    mv = n.statistics.market_value(components=["Generator", "Link"], groupby=False)
    comps = mv.index.get_level_values(0).unique()
    mv_by = {c: mv.xs(c, level=0) for c in comps}

    def df_comp(comp: str) -> pd.DataFrame:
        if comp == "Generator":
            table = n.generators
            bus_col = table.bus
            price_lookup = price_ts
            names = table.index
        elif comp == "Link":
            # keep only links where either bus0 or bus1 is AC/low-voltage
            ac_lv = set(n.buses.query("carrier in ['AC', 'low voltage']").index)
            table = n.links[n.links.bus0.isin(ac_lv) | n.links.bus1.isin(ac_lv)]
            names = table.index
            if table.empty:
                return None
            use_bus1 = table.bus1.isin(ac_lv)
            bus_col = pd.Series(table.bus0).where(~use_bus1, table.bus1)
            price_lookup = price_ts
        else:
            raise ValueError(f"Unexpected component: {comp}")

        mv_comp = mv_by.get(comp, pd.Series(index=names, dtype=float)).reindex(names)
        prices = price_lookup.reindex(columns=bus_col).set_axis(names, axis=1)
        avg_price = (
            (prices.multiply(weighted_load, axis=0).sum() / total_load)
            if total_load
            else pd.Series(0.0, index=names)
        )

        df = pd.DataFrame(
            {
                "name": names,
                "component": comp,
                "bus": bus_col.values,
                "carrier": table.carrier.values,
                "market_value_EUR_per_MWh": mv_comp.values,
                "average_price_EUR_per_MWh": avg_price.values,
            }
        )
        df["market_value_factor"] = (
            df["market_value_EUR_per_MWh"] / df["average_price_EUR_per_MWh"]
        )
        df.loc[df["average_price_EUR_per_MWh"] == 0, "market_value_factor"] = pd.NA
        return df

    frames = []
    for c in comps:
        df = df_comp(c)
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def main(network_path: Path, output_paths: Iterable[Path]) -> None:
    n = pypsa.Network(network_path)
    output_paths = list(output_paths)
    if len(output_paths) != 1:
        raise ValueError("Expected one output path.")
    gen_mv = market_value_by_generator(n)
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
