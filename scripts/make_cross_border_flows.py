# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Export energy flows across all at each snapshot.
"""

import logging

import numpy as np
import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def extract_flows_timeseries(n: pypsa.Network) -> pd.DataFrame:
    """
    Extract all connection flows at each snapshot.

    For AC lines (bidirectional by nature):
    - Positive flow: energy flows bus0 → bus1
    - Negative flow: energy flows bus1 → bus0

    For links (can be unidirectional or bidirectional):
    - Unidirectional (p_min_pu >= 0): always flow bus0 → bus1
    - Bidirectional (p_min_pu < 0): positive flows bus0 → bus1, negative flows bus1 → bus0

    Parameters
    ----------
    n : pypsa.Network
        Solved PyPSA network.

    Returns
    -------
    pd.DataFrame
        Columns: snapshot, from_bus, to_bus, carrier, flow_MW
    """
    # Process AC transmission lines for electricity flows
    lines_flows = (
        n.lines_t.p0.stack()
        .reset_index()
        .rename(columns={0: "flow_MW"})
        .merge(
            n.lines[["bus0", "bus1", "carrier"]],
            left_on="Line",
            right_index=True,
        )
        .assign(
            positive_flow=lambda df: df["flow_MW"] >= 0,
            from_bus=lambda df: np.where(df["positive_flow"], df["bus0"], df["bus1"]),
            to_bus=lambda df: np.where(df["positive_flow"], df["bus1"], df["bus0"]),
            flow_MW=lambda df: df["flow_MW"].abs(),
        )[["snapshot", "from_bus", "to_bus", "carrier", "flow_MW"]]
    )

    # Process links (DC, H2, sector coupling, etc.) for other energy carriers
    links_flows = (
        n.links_t.p0.stack()
        .reset_index()
        .rename(columns={0: "flow_MW"})
        .merge(
            n.links[["bus0", "bus1", "carrier", "efficiency", "p_min_pu"]],
            left_on="Link",
            right_index=True,
        )
        .assign(
            is_bidirectional=lambda df: df["p_min_pu"] < 0,
            positive_flow=lambda df: df["flow_MW"] >= 0,
            from_bus=lambda df: np.where(
                df["is_bidirectional"] & ~df["positive_flow"], df["bus1"], df["bus0"]
            ),
            to_bus=lambda df: np.where(
                df["is_bidirectional"] & ~df["positive_flow"], df["bus0"], df["bus1"]
            ),
            flow_MW=lambda df: (df["flow_MW"].abs() * df["efficiency"]),
        )[["snapshot", "from_bus", "to_bus", "carrier", "flow_MW"]]
    )

    # Combine all flows and sort
    df = pd.concat([lines_flows, links_flows], ignore_index=True).sort_values(
        ["snapshot", "from_bus", "to_bus", "carrier"]
    )

    return df


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "generate_cross_border_flows",
            clusters="adm",
            opts="",
            sector_opts="",
            planning_horizons="2025",
            run="walloon-model",
        )

    configure_logging(snakemake)
    set_scenario_config(snakemake)

    # Load network and extract flows
    n = pypsa.Network(snakemake.input.network)
    flows = extract_flows_timeseries(n)

    # Export results
    flows.to_csv(snakemake.output.flows, index=False)
