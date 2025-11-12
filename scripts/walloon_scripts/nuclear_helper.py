# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _apply_nuclear_costs_to_links(n, costs: pd.DataFrame) -> None:
    if "nuclear" not in costs.index:
        logger.warning(
            "Cost table does not contain a 'nuclear' entry; nuclear link costs left unchanged."
        )
        return

    mask = n.links.carrier.str.contains("nuclear", case=False)
    if not mask.any():
        logger.debug("No nuclear links found in the network.")
        return

    efficiency = n.links.loc[mask, "efficiency"]
    if "capital_cost" in costs.columns:
        n.links.loc[mask, "capital_cost"] = (
            efficiency * costs.at["nuclear", "capital_cost"]
        )
    if "VOM" in costs.columns:
        n.links.loc[mask, "marginal_cost"] = efficiency * costs.at["nuclear", "VOM"]
    logger.info("Updated %s nuclear link cost entries.", mask.sum())


def _set_links_extendable_for_nodes(
    n, nodes: list[str], planning_horizon: int
) -> None:
    if not nodes:
        return

    suffix = n.links.index.str.extract(r"^(?P<prefix>.+ nuclear)-(?P<year>\d{4})$")
    suffix = suffix.dropna()
    if suffix.empty:
        logger.debug("No nuclear link names with year suffix found.")
        return

    suffix["year"] = suffix["year"].astype(int)
    for node in nodes:
        prefix = f"{node} nuclear"
        matches = suffix[suffix["prefix"] == prefix]
        if matches.empty:
            logger.warning("No nuclear link found for node '%s'.", node)
            continue

        valid = matches[matches["year"] <= planning_horizon]
        if valid.empty:
            logger.warning(
                "Nuclear link for node '%s' only exists after planning horizon %s.",
                node,
                planning_horizon,
            )
            continue

        target_year = valid["year"].max()
        link_name = f"{prefix}-{target_year}"
        n.links.loc[link_name, "p_nom_extendable"] = True


def add_BEWAL_nuclear(
    n,
    walloon_nuclear_config,
    planning_horizon,
    costs: Optional[pd.DataFrame] = None,
    link_name: str = "BEWAL nuclear-2025",
    extendable_nodes: Optional[dict[int, list[str]]] = None,
):
    """
    Update the BEWAL nuclear link in the network to be extendable if 'nuclear' is
    listed for the given planning horizon and also update nuclear link costs from
    the processed cost table.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network object whose links are being modified.
    walloon_nuclear_config : dict
        Dictionary mapping planning horizon years (int) to lists of electricity
        carrier strings. Example:
            {2030: ['nuclear'], 2040: ['OCGT', 'nuclear']}
    planning_horizon : int
        The year to check and update.
    costs : pandas.DataFrame, optional
        Prepared cost table for the active planning horizon. When provided,
        capital and marginal costs for **all** nuclear links are refreshed using
        the table values so every nuclear asset reflects the desired overrides.
    link_name : str, optional
        Name of the Walloon nuclear link to adjust (default
        ``'BEWAL nuclear-2025'``).
    extendable_nodes : dict[int, list[str]], optional
        Mapping from planning horizon to nodes whose nuclear links should become
        extendable in that horizon (e.g., {"2040": ["FR", "DE"]}).
    """

    horizon_config = walloon_nuclear_config.get(planning_horizon, [])
    nodes_to_extend = []
    if extendable_nodes:
        nodes_to_extend = extendable_nodes.get(planning_horizon, [])
    link_missing = link_name not in n.links.index

    if costs is not None:
        _apply_nuclear_costs_to_links(n, costs)
    elif link_missing:
        logger.warning(
            "Requested nuclear link '%s' not found; unable to update costs.", link_name
        )

    if "nuclear" in horizon_config:
        if link_missing:
            logger.warning(
                "Requested nuclear link '%s' not found; extendable flag not updated.",
                link_name,
            )
        else:
            n.links.loc[link_name, "p_nom_extendable"] = True

    _set_links_extendable_for_nodes(n, nodes_to_extend, planning_horizon)

    non_nuclear_values = [v for v in horizon_config if v != "nuclear"]
    if non_nuclear_values:
        logger.warning(
            "The following conventional technologies are currently not supported as extendable: "
            f"{non_nuclear_values}. They will remain non-extendable.",
        )
