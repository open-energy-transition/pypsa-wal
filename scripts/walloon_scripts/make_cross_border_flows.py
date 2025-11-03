# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT
"""
Export energy flows (imports and exports) at each snapshot.
"""

import logging

import numpy as np
import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def extract_flows_timeseries(n: pypsa.Network) -> pd.DataFrame:
    """
    Extract all lines and links flows at each snapshot between different buses.

    For lines (bidirectional):
    - Positive flow: energy flows bus0 → bus1
    - Negative flow: energy flows bus1 → bus0

    For links (can be unidirectional or bidirectional):
    - Unidirectional (p_min_pu >= 0): always flow bus0 → bus1
    - Bidirectional (p_min_pu < 0):
        - positive flows bus0 → bus1
        - negative flows bus1 → bus0

    Parameters
    ----------
    n : pypsa.Network
        Solved PyPSA network.

    Returns
    -------
    pd.DataFrame
        Columns: snapshot, node_from, node_to, carrier, flow, unit_from, unit_to
        Only includes flows between different nodes (intra-node flows filtered out).
    """

    lines_flows = (
        n.lines_t.p0.multiply(n.snapshot_weightings.generators, axis=0)
        .stack()
        .reset_index()
        .rename(columns={0: "flow"})
        .merge(
            n.lines[["bus0", "bus1", "carrier"]],
            left_on="name",
            right_index=True,
        )
        .assign(
            positive_flow=lambda df: df["flow"] >= 0,
            bus_from=lambda df: np.where(df["positive_flow"], df["bus0"], df["bus1"]),
            bus_to=lambda df: np.where(df["positive_flow"], df["bus1"], df["bus0"]),
            flow=lambda df: df["flow"].abs(),
        )[
            [
                "snapshot",
                "bus_from",
                "bus_to",
                "carrier",
                "flow",
            ]
        ]
    )

    links_flows = (
        n.links_t.p0.multiply(n.snapshot_weightings.generators, axis=0)
        .stack()
        .reset_index()
        .rename(columns={0: "flow"})
        .merge(
            n.links[["bus0", "bus1", "carrier", "p_min_pu"]],
            left_on="name",
            right_index=True,
        )
        .assign(
            is_bidirectional=lambda df: df["p_min_pu"] < 0,
            positive_flow=lambda df: df["flow"] >= 0,
            bus_from=lambda df: np.where(
                df["is_bidirectional"] & ~df["positive_flow"], df["bus1"], df["bus0"]
            ),
            bus_to=lambda df: np.where(
                df["is_bidirectional"] & ~df["positive_flow"], df["bus0"], df["bus1"]
            ),
            flow=lambda df: df["flow"].abs(),
        )
        .merge(
            n.buses[["unit"]].rename(columns={"unit": "unit_from"}),
            left_on="bus_from",
            right_index=True,
        )
        .merge(
            n.buses[["unit"]].rename(columns={"unit": "unit_to"}),
            left_on="bus_to",
            right_index=True,
        )[
            [
                "snapshot",
                "bus_from",
                "bus_to",
                "carrier",
                "flow",
            ]
        ]
    )

    df = (
        pd.concat([lines_flows, links_flows], ignore_index=True)
        .query("bus_from != bus_to")[
            [
                "snapshot",
                "bus_from",
                "bus_to",
                "carrier",
                "flow",
            ]
        ]
        .sort_values(["snapshot", "bus_from", "bus_to", "carrier"])
    ).reset_index(drop=True)

    # Merge with units
    df = df.merge(
        n.buses[["unit"]].rename(columns={"unit": "unit_from"}),
        left_on="bus_from",
        right_index=True,
    ).merge(
        n.buses[["unit"]].rename(columns={"unit": "unit_to"}),
        left_on="bus_to",
        right_index=True,
    )[
        [
            "snapshot",
            "bus_from",
            "bus_to",
            "carrier",
            "unit_from",
            "unit_to",
            "flow",
        ]
    ]

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
