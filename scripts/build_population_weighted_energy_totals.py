# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Distribute country-level energy demands by population.
"""

import logging

import pandas as pd

from scripts._helpers import configure_logging, get_snapshots, set_scenario_config

idx = pd.IndexSlice

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "build_population_weighted_energy_totals",
            kind="heat",
            clusters=60,
            planning_horizons="2030",
        )
    configure_logging(snakemake)
    set_scenario_config(snakemake)

    config = snakemake.config
    study = config["run"]["name"]

    if snakemake.wildcards.kind == "heat":
        snapshots = get_snapshots(
            snakemake.params.snapshots, snakemake.params.drop_leap_day
        )
        data_years = snapshots.year.unique()
    else:
        data_years = int(config["energy"]["energy_totals_year"])

    pop_layout = pd.read_csv(snakemake.input.clustered_pop_layout, index_col=0)

    totals = pd.read_csv(snakemake.input.energy_totals, index_col=[0, 1])
    totals = totals.loc[idx[:, data_years], :].groupby("country").mean()

    nodal_totals = totals.loc[pop_layout.ct].fillna(0.0)
    nodal_totals.index = pop_layout.index
    nodal_totals = nodal_totals.multiply(pop_layout.fraction, axis=0)
    if study == "walloon-model":
        wallon_node = config["run"]["wallon_node"]
        flemish_node = config["run"]["flemish_node"]
        #Adding wallon region international navigation demand to Flanders
        if snakemake.wildcards.kind != "heat":
           wal_int_nav = nodal_totals.loc[wallon_node, "total international navigation"]
           nodal_totals.loc[flemish_node, "total international navigation"] += wal_int_nav
        wallon_demands = pd.read_csv(snakemake.input.wallon_demands, index_col=0)[["TWh"]]
        common_cols = nodal_totals.columns.intersection(wallon_demands.index)
        extract_demands = wallon_demands.loc[common_cols].squeeze()
        nodal_totals.loc[wallon_node, common_cols] = extract_demands
    else:
        logger.info("Skipping Walloon adjustments — study mode not active.")

    nodal_totals.to_csv(snakemake.output[0])
