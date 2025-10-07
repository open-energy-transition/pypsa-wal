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
- cross_border_flows_timeseries.csv: Full time series of flows with node/region/country detail
- cross_border_flows_summary.csv: Time-aggregated totals by country/carrier
- cross_border_flows_bilateral.csv: Country-to-country bilateral flows
- cross_border_flows_regional_summary.csv: Time-aggregated totals by region/carrier
- cross_border_flows_regional_bilateral.csv: Region-to-region bilateral flows
"""

import logging

import numpy as np
import pandas as pd
import pypsa

from scripts._helpers import configure_logging, set_scenario_config

logger = logging.getLogger(__name__)


def extract_region_from_bus(bus_name: str, country: str) -> str:
    """
    Extract region identifier from bus name.

    For Belgian NUTS-1 regions (BEWAL, BEBRU, BEVLG), returns the specific region.
    For other countries, returns the country code.
    Handles special bus names like "BEWAL H2", "FR battery", etc.

    Parameters
    ----------
    bus_name : str
        Name of the bus (e.g., "BEWAL", "BEBRU H2", "FR", "DE battery")
    country : str
        Country code from bus.country attribute (may be NaN)

    Returns
    -------
    str
        Region identifier (e.g., "BEWAL", "BEBRU", "BEVLG", "FR", "DE")
    """
    if pd.isna(bus_name) or bus_name == "":
        return country if pd.notna(country) else "Unknown"

    bus_str = str(bus_name).strip()

    # Handle Belgian NUTS-1 regions
    if bus_str.startswith('BEWAL'):
        return 'BEWAL'
    elif bus_str.startswith('BEBRU'):
        return 'BEBRU'
    elif bus_str.startswith('BEVLG'):
        return 'BEVLG'

    # For other buses, try to extract country code
    if pd.notna(country) and country != "":
        return country

    # Fallback: extract first 2 characters as country code
    # This works for buses like "FR", "DE", "NL", "FR H2", "DE battery", etc.
    parts = bus_str.split()
    if len(parts[0]) >= 2:
        return parts[0][:2]

    return "Unknown"


def identify_cross_border_connections(n: pypsa.Network) -> dict:
    """
    Identify all transmission lines and links (including intra-country flows).

    Captures ALL connections to enable node-level and regional analysis.
    Adds node, region, and country information for both endpoints.

    Parameters
    ----------
    n : pypsa.Network
        Optimized network with solved flows

    Returns
    -------
    dict
        Dictionary with keys 'lines' and 'links', each containing DataFrames
        with columns: node0, node1, region0, region1, country0, country1
    """
    all_connections = {}

    # Process AC transmission lines
    lines = n.lines.copy()
    lines["node0"] = lines.bus0
    lines["node1"] = lines.bus1
    lines["country0"] = lines.bus0.map(n.buses.country)
    lines["country1"] = lines.bus1.map(n.buses.country)

    # Extract regions using helper function
    lines["region0"] = lines.apply(
        lambda row: extract_region_from_bus(row.bus0, row.country0), axis=1
    )
    lines["region1"] = lines.apply(
        lambda row: extract_region_from_bus(row.bus1, row.country1), axis=1
    )

    all_connections["lines"] = lines

    logger.info(f"Found {len(lines)} AC transmission lines")

    # Process links (DC, H2, heat, etc.)
    links = n.links.copy()
    links["node0"] = links.bus0
    links["node1"] = links.bus1
    links["country0"] = links.bus0.map(n.buses.country)
    links["country1"] = links.bus1.map(n.buses.country)

    # Extract regions using helper function
    links["region0"] = links.apply(
        lambda row: extract_region_from_bus(row.bus0, row.country0), axis=1
    )
    links["region1"] = links.apply(
        lambda row: extract_region_from_bus(row.bus1, row.country1), axis=1
    )

    all_connections["links"] = links

    logger.info(
        f"Found {len(links)} links "
        f"({links.carrier.value_counts().to_dict()})"
    )

    return all_connections


def calculate_cross_border_flows_timeseries(n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate time series of energy flows for all connections.

    For each connection, flows are attributed to both endpoints with node, region,
    and country information. Positive values indicate imports, negative values
    indicate exports.

    Parameters
    ----------
    n : pypsa.Network
        Optimized network with solved flows

    Returns
    -------
    pd.DataFrame
        Time series with columns: timestamp, node, region, country, carrier,
        import_MW, export_MW, net_MW, connection_type, connection_id
    """
    all_connections = identify_cross_border_connections(n)

    # Initialize results list
    results = []

    # Get snapshot weights for energy calculation
    snapshot_weights = n.snapshot_weightings.generators

    # Process AC transmission lines
    if not all_connections["lines"].empty:
        logger.info("Processing AC transmission line flows...")

        for line_id, line in all_connections["lines"].iterrows():
            # p0 is power flow at bus0 (positive = flowing away from bus0)
            # p1 is power flow at bus1 (should be -p0 for lossless lines)
            flow_at_bus0 = n.lines_t.p0[line_id]

            # Positive flow means power flows from bus0 to bus1
            # This is an export from node0/region0/country0 and import to node1/region1/country1
            for snapshot in flow_at_bus0.index:
                flow = flow_at_bus0.loc[snapshot]

                if flow > 0:
                    # Flow from node0 to node1
                    # Export from node0
                    results.append(
                        {
                            "timestamp": snapshot,
                            "node": line.node0,
                            "region": line.region0,
                            "country": line.country0,
                            "carrier": line.carrier,
                            "import_MW": 0.0,
                            "export_MW": flow,
                            "net_MW": -flow,
                            "connection_type": "line",
                            "connection_id": line_id,
                        }
                    )
                    # Import to node1
                    results.append(
                        {
                            "timestamp": snapshot,
                            "node": line.node1,
                            "region": line.region1,
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
                    # Flow from node1 to node0
                    # Import to node0
                    results.append(
                        {
                            "timestamp": snapshot,
                            "node": line.node0,
                            "region": line.region0,
                            "country": line.country0,
                            "carrier": line.carrier,
                            "import_MW": -flow,
                            "export_MW": 0.0,
                            "net_MW": -flow,
                            "connection_type": "line",
                            "connection_id": line_id,
                        }
                    )
                    # Export from node1
                    results.append(
                        {
                            "timestamp": snapshot,
                            "node": line.node1,
                            "region": line.region1,
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
    if not all_connections["links"].empty:
        logger.info("Processing link flows...")

        for link_id, link in all_connections["links"].iterrows():
            # p0 is power/energy flow at bus0
            # For links, positive p0 means power is consumed from bus0
            if link_id not in n.links_t.p0.columns:
                continue

            flow_at_bus0 = n.links_t.p0[link_id]

            for snapshot in flow_at_bus0.index:
                flow = flow_at_bus0.loc[snapshot]

                if flow > 0:
                    # Link is active, consuming from bus0, producing at bus1
                    # Export from node0/region0/country0, import to node1/region1/country1
                    results.append(
                        {
                            "timestamp": snapshot,
                            "node": link.node0,
                            "region": link.region0,
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
                            "node": link.node1,
                            "region": link.region1,
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


def aggregate_timeseries_by_region_carrier(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate flows by region, carrier, and timestamp.

    Combines multiple connections into single region-carrier-timestamp entries.
    Enables analysis of specific regional flows (e.g., BEWAL, BEBRU, BEVLG).

    Parameters
    ----------
    df : pd.DataFrame
        Detailed flow records from calculate_cross_border_flows_timeseries

    Returns
    -------
    pd.DataFrame
        Aggregated time series with columns: timestamp, region, carrier, import_MW, export_MW, net_MW
    """
    if df.empty:
        return df

    # Group by timestamp, region, carrier
    grouped = (
        df.groupby(["timestamp", "region", "carrier"])
        .agg({"import_MW": "sum", "export_MW": "sum", "net_MW": "sum"})
        .reset_index()
    )

    # Sort for readability
    grouped = grouped.sort_values(["timestamp", "region", "carrier"])

    logger.info(f"Aggregated to {len(grouped)} region-carrier-timestamp combinations")

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


def calculate_regional_summary(df: pd.DataFrame, n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate time-aggregated summary of flows by region.

    Converts MW to MWh using snapshot weightings and aggregates over time period.
    Enables analysis of specific regional flows (e.g., BEWAL, BEBRU, BEVLG).

    Parameters
    ----------
    df : pd.DataFrame
        Time series from aggregate_timeseries_by_region_carrier
    n : pypsa.Network
        Network for snapshot weightings

    Returns
    -------
    pd.DataFrame
        Summary with columns: region, carrier, total_import_MWh, total_export_MWh, net_MWh
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "region",
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
        df_with_weights.groupby(["region", "carrier"])
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

    summary = summary.sort_values(["region", "carrier"])

    logger.info(f"Created summary for {len(summary)} region-carrier combinations")

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
        # Aggregate multiple connections between same country pairs
        bilateral_df = (
            bilateral_df.groupby(["from_country", "to_country", "carrier"])
            .agg({"total_MWh": "sum"})
            .reset_index()
        )
        bilateral_df = bilateral_df.sort_values(
            ["from_country", "to_country", "carrier"]
        )

    logger.info(f"Created {len(bilateral_df)} bilateral flow entries")

    return bilateral_df


def calculate_regional_bilateral_flows(df: pd.DataFrame, n: pypsa.Network) -> pd.DataFrame:
    """
    Calculate bilateral region-to-region flows by carrier.

    Shows which regions trade energy with each other (e.g., BEWAL to BEBRU,
    BEWAL to FR, etc.).

    Parameters
    ----------
    df : pd.DataFrame
        Detailed flow records from calculate_cross_border_flows_timeseries
    n : pypsa.Network
        Network for snapshot weightings and connection metadata

    Returns
    -------
    pd.DataFrame
        Bilateral flows with columns: from_region, to_region, carrier, total_MWh
    """
    if df.empty:
        return pd.DataFrame(
            columns=["from_region", "to_region", "carrier", "total_MWh"]
        )

    all_connections = identify_cross_border_connections(n)

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

        # Get region mapping
        if connection_type == "line":
            conn = all_connections["lines"].loc[connection_id]
        else:
            conn = all_connections["links"].loc[connection_id]

        region0 = conn.region0
        region1 = conn.region1
        carrier = conn.carrier

        # Calculate net flow from region0 to region1
        # Positive export from region0 = flow to region1
        region0_flows = connection_flows[connection_flows.region == region0]
        total_export_mwh = (region0_flows.export_MW * region0_flows.weight).sum()

        if total_export_mwh > 0:
            bilateral_results.append(
                {
                    "from_region": region0,
                    "to_region": region1,
                    "carrier": carrier,
                    "total_MWh": total_export_mwh,
                }
            )

        # Calculate reverse flow
        region1_flows = connection_flows[connection_flows.region == region1]
        total_export_mwh_reverse = (
            region1_flows.export_MW * region1_flows.weight
        ).sum()

        if total_export_mwh_reverse > 0:
            bilateral_results.append(
                {
                    "from_region": region1,
                    "to_region": region0,
                    "carrier": carrier,
                    "total_MWh": total_export_mwh_reverse,
                }
            )

    bilateral_df = pd.DataFrame(bilateral_results)

    if not bilateral_df.empty:
        # Aggregate multiple connections between same region pairs
        bilateral_df = (
            bilateral_df.groupby(["from_region", "to_region", "carrier"])
            .agg({"total_MWh": "sum"})
            .reset_index()
        )
        bilateral_df = bilateral_df.sort_values(
            ["from_region", "to_region", "carrier"]
        )

    logger.info(f"Created {len(bilateral_df)} regional bilateral flow entries")

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

    # Calculate regional aggregations
    logger.info("Aggregating by region...")
    regional_timeseries = aggregate_timeseries_by_region_carrier(detailed_flows)

    logger.info("Calculating regional summary...")
    regional_summary = calculate_regional_summary(regional_timeseries, n)

    logger.info("Calculating regional bilateral flows...")
    regional_bilateral = calculate_regional_bilateral_flows(detailed_flows, n)

    # Export country-level results
    logger.info(f"Exporting country time series to {snakemake.output.timeseries}")
    timeseries.to_csv(snakemake.output.timeseries, index=False)

    logger.info(f"Exporting country summary to {snakemake.output.summary}")
    summary.to_csv(snakemake.output.summary, index=False)

    logger.info(f"Exporting country bilateral flows to {snakemake.output.bilateral}")
    bilateral.to_csv(snakemake.output.bilateral, index=False)

    # Export regional results
    logger.info(f"Exporting regional time series to {snakemake.output.regional_timeseries}")
    regional_timeseries.to_csv(snakemake.output.regional_timeseries, index=False)

    logger.info(f"Exporting regional summary to {snakemake.output.regional_summary}")
    regional_summary.to_csv(snakemake.output.regional_summary, index=False)

    logger.info(f"Exporting regional bilateral flows to {snakemake.output.regional_bilateral}")
    regional_bilateral.to_csv(snakemake.output.regional_bilateral, index=False)

    logger.info("Cross-border flows export completed successfully!")
