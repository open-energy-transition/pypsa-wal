# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Export energy flows across all network connections at each timestep.
"""

import logging

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def extract_flows_timeseries(n: pypsa.Network) -> pd.DataFrame:
    """
    Extract all connection flows at each timestep.

    Parameters
    ----------
    n : pypsa.Network
        Solved PyPSA network.

    Returns
    -------
    pd.DataFrame
        Columns: timestamp, from_bus, to_bus, carrier, flow_MW
    """
    results = []

    # Process AC transmission lines for electricity flows
    for line_id, line in n.lines.iterrows():
        if line_id not in n.lines_t.p0.columns:
            continue

        flows = n.lines_t.p0[line_id]
        for timestamp, flow_mw in flows.items():
            if flow_mw != 0:  # Skip zero flows
                # Positive flow = from bus0 to bus1
                from_bus = line.bus0 if flow_mw > 0 else line.bus1
                to_bus = line.bus1 if flow_mw > 0 else line.bus0
                results.append(
                    {
                        "timestamp": timestamp,
                        "from_bus": from_bus,
                        "to_bus": to_bus,
                        "carrier": line.carrier,
                        "flow_MW": abs(flow_mw),
                    }
                )

    # Process links (DC, H2, sector coupling, etc.) for other energy carriers
    for link_id, link in n.links.iterrows():
        if link_id not in n.links_t.p0.columns:
            continue

        flows = n.links_t.p0[link_id]
        for timestamp, flow_mw in flows.items():
            if flow_mw > 0:  # Links are unidirectional, only positive flows matter
                # Account for efficiency losses
                output_mw = flow_mw * link.efficiency
                results.append(
                    {
                        "timestamp": timestamp,
                        "from_bus": link.bus0,
                        "to_bus": link.bus1,
                        "carrier": link.carrier,
                        "flow_MW": output_mw,
                    }
                )

    df = pd.DataFrame(results)

    # Sort for readability
    df = df.sort_values(["timestamp", "from_bus", "to_bus", "carrier"])

    logger.info(
        f"Extracted {len(df)} flow records across {len(df.timestamp.unique())} timesteps"
    )

    return df


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "export_cross_border_flows",
            clusters="adm",
            opts="",
            sector_opts="",
            planning_horizons="2025",
            run="walloon-model",
        )

    configure_logging(snakemake)
    set_scenario_config(snakemake)

    # Load network and extract flows
    logger.info(f"Loading network from {snakemake.input.network}")
    n = pypsa.Network(snakemake.input.network)
    flows = extract_flows_timeseries(n)

    # Export results
    logger.info(f"Exporting flows to {snakemake.output.flows}")
    flows.to_csv(snakemake.output.flows, index=False)
