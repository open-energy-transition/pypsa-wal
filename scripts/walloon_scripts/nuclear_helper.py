# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def add_BEWAL_nuclear(
    n,
    planning_horizon,
    extendable_nuclear_nodes: dict = {2040: ["BEWAL"], 2050: ["BEWAL"]},
):
    """
    Update the BEWAL nuclear link in the network to be extendable if 'nuclear' is
    listed for the given planning horizon and also update nuclear link costs from
    the processed cost table.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network object whose links are being modified.
    planning_horizon : int
        The year to check and update.
    extendable_nuclear_nodes : Dict
        Dict, with planning horizons as keys, passing a list of name of the buses where the nuclear link shall be set to extendable
        (default ``{2040: ["BEWAL"], 2050: ["BEWAL"]}``).
    """

    if planning_horizon in extendable_nuclear_nodes.keys():
        extendable_nuclear_links = [f"{bus} nuclear-2025" for bus in extendable_nuclear_nodes[planning_horizon]]
        link_missing = [link for link in extendable_nuclear_links if link not in n.links.index]
        extendable_nuclear_links = list(set(extendable_nuclear_links) - set(link_missing))

        if link_missing != []:
            logger.warning(
                "Requested nuclear link '%s' not found; unable to update costs.", link_missing
            )

        if extendable_nuclear_links != []:
            n.links.loc[extendable_nuclear_links, "p_nom_extendable"] = True


def retrofit_retired_nuclear(
        n,
        decomissioned_nuclear,
        planning_horizon,
        costs,
        extendable_nuclear_nodes = ["BEWAL", "BEVLG"],
        retrofit_nuclear_once: bool = False,
        MILP = False):
    """
    Provide the option to a given set of nuclear links that are being decomissioned to be retrofitted
    and remain in the system.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network object where retrofit nuclear links are being added.
    decomissioned_nuclear : pypsa.Network
        A PyPSA network object that contains only links of generators that are
        being decommissioned in the considered planning horizon.
    planning_horizon : int
        Will become the new build_year of the retrofitted plant.
    extendable_nuclear_nodes : list
        list ofs name of the buses where the nuclear link shall be made
        available for retrofitting (default ``["BEWAL"]``).
    MILP : bool
        True will only allow retrofitting the entire block or nothing at all
        Turning the problem essentially into a MILP.
    """
    if planning_horizon < 2040:
        logger.info(
            "Skipping nuclear retrofit: planning horizon %s is before the retrofit window.",
            planning_horizon,
        )
        return

    decomissioned_nuclear = decomissioned_nuclear.query("bus1 in @extendable_nuclear_nodes")
    if retrofit_nuclear_once:
        decomissioned_nuclear = decomissioned_nuclear[
            ~decomissioned_nuclear.index.str.contains("retrofit")
        ]
    retrofit_nuclear = decomissioned_nuclear.copy()
    retrofit_nuclear.index = retrofit_nuclear.index.astype(str) + " retrofit"
    retrofit_nuclear["p_nom_max"] = (
        retrofit_nuclear[["p_nom", "p_nom_opt"]]
        .apply(pd.to_numeric, errors="coerce")
        .max(axis=1)
        .fillna(0.0)
    )
    if MILP:
        retrofit_nuclear["p_nom_mod"] = retrofit_nuclear["p_nom_max"]
    retrofit_nuclear[["p_nom_opt", "p_nom", "p_nom_min"]] = 0.1
    retrofit_nuclear["p_nom_extendable"] = True
    retrofit_nuclear["build_year"] = planning_horizon

    # insert retrofit lifetime + capital cost here (take from costs_processed.csv, ideally represented as a separate technology "nuclear retrofit"?
    # in that case, add a new input argument costs. Otherwise, hardcode below
    lifetime_nuclear_retro = costs.loc["nuclear retrofit"].loc["lifetime"]
    capital_cost_nuclear_retro = costs.loc["nuclear retrofit"].loc["capital_cost"]
    retrofit_nuclear["lifetime"] = lifetime_nuclear_retro
    retrofit_nuclear["capital_cost"] = (capital_cost_nuclear_retro * retrofit_nuclear["efficiency"])

    logger.info(
        f"Adding the option to retrofit the following nuclear plants: {decomissioned_nuclear.index} "
        f"to increase their lifetime by {lifetime_nuclear_retro} years. "
        f"Assuming an annualized cost of capital of {capital_cost_nuclear_retro}."
    )

    for name, row in retrofit_nuclear.iterrows():
        attrs = row.dropna().to_dict()
        n.add("Link", name=name, **attrs)
