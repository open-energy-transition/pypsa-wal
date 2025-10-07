#!/usr/bin/env python3
# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Export cross-border energy import/export flows at each timestep.

This script extracts time series data for energy flows across country borders
from optimized PyPSA network results. It processes both AC transmission lines
and DC/H2/sector coupling links to provide comprehensive cross-border flow data.

Outputs
-------
- cross_border_flows_timeseries.csv: Full time series of flows by country/carrier
- cross_border_flows_summary.csv: Time-aggregated totals by country/carrier
- cross_border_flows_bilateral.csv: Country-to-country bilateral flows
"""

import logging

import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def identify_cross_border_connections(n: pypsa.Network) -> dict:
    """
    Identify all transmission lines and links that cross country borders.

    Parameters
    ----------
    n : pypsa.Network
        Optimized network with solved flows

    Returns
    -------
    dict
        Dictionary with keys 'lines' and 'links', each containing DataFrames
        of cross-border connections with added country columns
    """
    cross_border = {}

    # Process AC transmission lines
    lines = n.lines.copy()
    lines["country0"] = lines.bus0.map(n.buses.country)
    lines["country1"] = lines.bus1.map(n.buses.country)
    cross_border_lines = lines[lines.country0 != lines.country1].copy()
    cross_border["lines"] = cross_border_lines

    logger.info(f"Found {len(cross_border_lines)} cross-border AC transmission lines")

    # Process links (DC, H2, heat, etc.)
    links = n.links.copy()
    links["country0"] = links.bus0.map(n.buses.country)
    links["country1"] = links.bus1.map(n.buses.country)
    cross_border_links = links[links.country0 != links.country1].copy()
    cross_border["links"] = cross_border_links

    logger.info(
        f"Found {len(cross_border_links)} cross-border links "
        f"({cross_border_links.carrier.value_counts().to_dict()})"
    )

    return cross_border


def calculate_cross_border_flows_timeseries(n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate time series of cross-border energy flows for each country and carrier.

    For each cross-border connection, flows are attributed to the importing and
    exporting countries. Positive values indicate imports, negative values indicate
    exports.

    Parameters
    ----------
    n : pypsa.Network
        Optimized network with solved flows

    Returns
    -------
    pd.DataFrame
        Time series with columns: timestamp, country, carrier, import_MW, export_MW, net_MW
    """
    cross_border = identify_cross_border_connections(n)

    # Initialize results list
    results = []

    # Get snapshot weights for energy calculation
    snapshot_weights = n.snapshot_weightings.generators

    # Process AC transmission lines
    if not cross_border["lines"].empty:
        logger.info("Processing AC transmission line flows...")

        for line_id, line in cross_border["lines"].iterrows():
            # p0 is power flow at bus0 (positive = flowing away from bus0)
            # p1 is power flow at bus1 (should be -p0 for lossless lines)
            flow_at_bus0 = n.lines_t.p0[line_id]

            # Positive flow means power flows from bus0 to bus1
            # This is an export from country0 and import to country1
            for snapshot in flow_at_bus0.index:
                flow = flow_at_bus0.loc[snapshot]

                if flow > 0:
                    # Flow from country0 to country1
                    # Export from country0
                    results.append(
                        {
                            "timestamp": snapshot,
                            "country": line.country0,
                            "carrier": line.carrier,
                            "import_MW": 0.0,
                            "export_MW": flow,
                            "net_MW": -flow,
                            "connection_type": "line",
                            "connection_id": line_id,
                        }
                    )
                    # Import to country1
                    results.append(
                        {
                            "timestamp": snapshot,
                            "country": line.country1,
                            "carrier": line.carrier,
                            "import_MW": flow,
                            "export_MW": 0.0,
                            "net_MW": flow,
                            "connection_type": "line",
                            "connection_id": line_id,
                        }
                    )
                elif flow < 0:
                    # Flow from country1 to country0
                    # Import to country0
                    results.append(
                        {
                            "timestamp": snapshot,
                            "country": line.country0,
                            "carrier": line.carrier,
                            "import_MW": -flow,
                            "export_MW": 0.0,
                            "net_MW": -flow,
                            "connection_type": "line",
                            "connection_id": line_id,
                        }
                    )
                    # Export from country1
                    results.append(
                        {
                            "timestamp": snapshot,
                            "country": line.country1,
                            "carrier": line.carrier,
                            "import_MW": 0.0,
                            "export_MW": -flow,
                            "net_MW": flow,
                            "connection_type": "line",
                            "connection_id": line_id,
                        }
                    )

    # Process links (DC, H2, etc.)
    if not cross_border["links"].empty:
        logger.info("Processing cross-border link flows...")

        for link_id, link in cross_border["links"].iterrows():
            # p0 is power/energy flow at bus0
            # For links, positive p0 means power is consumed from bus0
            if link_id not in n.links_t.p0.columns:
                continue

            flow_at_bus0 = n.links_t.p0[link_id]

            for snapshot in flow_at_bus0.index:
                flow = flow_at_bus0.loc[snapshot]

                if flow > 0:
                    # Link is active, consuming from bus0, producing at bus1
                    # Export from country0, import to country1
                    results.append(
                        {
                            "timestamp": snapshot,
                            "country": link.country0,
                            "carrier": link.carrier,
                            "import_MW": 0.0,
                            "export_MW": flow,
                            "net_MW": -flow,
                            "connection_type": "link",
                            "connection_id": link_id,
                        }
                    )
                    # Account for efficiency losses
                    output_power = flow * link.efficiency
                    results.append(
                        {
                            "timestamp": snapshot,
                            "country": link.country1,
                            "carrier": link.carrier,
                            "import_MW": output_power,
                            "export_MW": 0.0,
                            "net_MW": output_power,
                            "connection_type": "link",
                            "connection_id": link_id,
                        }
                    )

    df = pd.DataFrame(results)

    if df.empty:
        logger.warning("No cross-border flows found!")
        return df

    logger.info(
        f"Extracted {len(df)} individual flow records across {len(df.timestamp.unique())} timesteps"
    )

    return df


def aggregate_timeseries_by_country_carrier(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate cross-border flows by country, carrier, and timestamp.

    Combines multiple connections into single country-carrier-timestamp entries.

    Parameters
    ----------
    df : pd.DataFrame
        Detailed flow records from calculate_cross_border_flows_timeseries

    Returns
    -------
    pd.DataFrame
        Aggregated time series with columns: timestamp, country, carrier, import_MW, export_MW, net_MW
    """
    if df.empty:
        return df

    # Group by timestamp, country, carrier
    grouped = (
        df.groupby(["timestamp", "country", "carrier"])
        .agg({"import_MW": "sum", "export_MW": "sum", "net_MW": "sum"})
        .reset_index()
    )

    # Sort for readability
    grouped = grouped.sort_values(["timestamp", "country", "carrier"])

    logger.info(f"Aggregated to {len(grouped)} country-carrier-timestamp combinations")

    return grouped


def calculate_summary(df: pd.DataFrame, n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate time-aggregated summary of cross-border flows.

    Converts MW to MWh using snapshot weightings and aggregates over time period.

    Parameters
    ----------
    df : pd.DataFrame
        Time series from aggregate_timeseries_by_country_carrier
    n : pypsa.Network
        Network for snapshot weightings

    Returns
    -------
    pd.DataFrame
        Summary with columns: country, carrier, total_import_MWh, total_export_MWh, net_MWh
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "country",
                "carrier",
                "total_import_MWh",
                "total_export_MWh",
                "net_MWh",
            ]
        )

    # Add snapshot weights to convert MW to MWh
    df_with_weights = df.copy()
    df_with_weights["weight"] = df_with_weights.timestamp.map(
        n.snapshot_weightings.generators
    )

    # Convert MW to MWh
    df_with_weights["import_MWh"] = (
        df_with_weights["import_MW"] * df_with_weights["weight"]
    )
    df_with_weights["export_MWh"] = (
        df_with_weights["export_MW"] * df_with_weights["weight"]
    )
    df_with_weights["net_MWh"] = df_with_weights["net_MW"] * df_with_weights["weight"]

    # Aggregate over time
    summary = (
        df_with_weights.groupby(["country", "carrier"])
        .agg(
            {
                "import_MWh": "sum",
                "export_MWh": "sum",
                "net_MWh": "sum",
            }
        )
        .reset_index()
    )

    summary.rename(
        columns={
            "import_MWh": "total_import_MWh",
            "export_MWh": "total_export_MWh",
            "net_MWh": "net_MWh",
        },
        inplace=True,
    )

    summary = summary.sort_values(["country", "carrier"])

    logger.info(f"Created summary for {len(summary)} country-carrier combinations")

    return summary


def calculate_bilateral_flows(df: pd.DataFrame, n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate bilateral country-to-country flows by carrier.

    Shows which countries trade energy with each other.

    Parameters
    ----------
    df : pd.DataFrame
        Detailed flow records from calculate_cross_border_flows_timeseries
    n : pypsa.Network
        Network for snapshot weightings and connection metadata

    Returns
    -------
    pd.DataFrame
        Bilateral flows with columns: from_country, to_country, carrier, total_MWh
    """
    if df.empty:
        return pd.DataFrame(
            columns=["from_country", "to_country", "carrier", "total_MWh"]
        )

    cross_border = identify_cross_border_connections(n)

    bilateral_results = []

    # Add snapshot weights
    df_with_weights = df.copy()
    df_with_weights["weight"] = df_with_weights.timestamp.map(
        n.snapshot_weightings.generators
    )

    # Process each connection
    for connection_id in df_with_weights.connection_id.unique():
        connection_flows = df_with_weights[
            df_with_weights.connection_id == connection_id
        ]

        if connection_flows.empty:
            continue

        connection_type = connection_flows.iloc[0].connection_type

        # Get country mapping
        if connection_type == "line":
            conn = cross_border["lines"].loc[connection_id]
        else:
            conn = cross_border["links"].loc[connection_id]

        country0 = conn.country0
        country1 = conn.country1
        carrier = conn.carrier

        # Calculate net flow from country0 to country1
        # Positive export from country0 = flow to country1
        country0_flows = connection_flows[connection_flows.country == country0]
        total_export_mwh = (country0_flows.export_MW * country0_flows.weight).sum()

        if total_export_mwh > 0:
            bilateral_results.append(
                {
                    "from_country": country0,
                    "to_country": country1,
                    "carrier": carrier,
                    "total_MWh": total_export_mwh,
                }
            )

        # Calculate reverse flow
        country1_flows = connection_flows[connection_flows.country == country1]
        total_export_mwh_reverse = (
            country1_flows.export_MW * country1_flows.weight
        ).sum()

        if total_export_mwh_reverse > 0:
            bilateral_results.append(
                {
                    "from_country": country1,
                    "to_country": country0,
                    "carrier": carrier,
                    "total_MWh": total_export_mwh_reverse,
                }
            )

    bilateral_df = pd.DataFrame(bilateral_results)

    if not bilateral_df.empty:
        bilateral_df = bilateral_df.sort_values(
            ["from_country", "to_country", "carrier"]
        )

    logger.info(f"Created {len(bilateral_df)} bilateral flow entries")

    return bilateral_df


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

    # Load optimized network
    logger.info(f"Loading network from {snakemake.input.network}")
    n = pypsa.Network(snakemake.input.network)

    # Calculate cross-border flows
    logger.info("Calculating cross-border flows...")
    detailed_flows = calculate_cross_border_flows_timeseries(n)

    # Aggregate by country, carrier, timestamp
    logger.info("Aggregating time series...")
    timeseries = aggregate_timeseries_by_country_carrier(detailed_flows)

    # Calculate summary
    logger.info("Calculating time-aggregated summary...")
    summary = calculate_summary(timeseries, n)

    # Calculate bilateral flows
    logger.info("Calculating bilateral flows...")
    bilateral = calculate_bilateral_flows(detailed_flows, n)

    # Export results
    logger.info(f"Exporting time series to {snakemake.output.timeseries}")
    timeseries.to_csv(snakemake.output.timeseries, index=False)

    logger.info(f"Exporting summary to {snakemake.output.summary}")
    summary.to_csv(snakemake.output.summary, index=False)

    logger.info(f"Exporting bilateral flows to {snakemake.output.bilateral}")
    bilateral.to_csv(snakemake.output.bilateral, index=False)

    logger.info("Cross-border flows export completed successfully!")
