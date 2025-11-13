# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import logging

import pandas as pd

logger = logging.getLogger(__name__)

def add_BEWAL_nuclear(
    n,
    walloon_nuclear_config,
    planning_horizon,
    link_name: str = "BEWAL nuclear-2025",
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
    link_name : str, optional
        Name of the Walloon nuclear link to adjust (default
        ``'BEWAL nuclear-2025'``).
    """

    horizon_config = walloon_nuclear_config.get(planning_horizon, [])
    link_missing = link_name not in n.links.index

    if link_missing:
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

    non_nuclear_values = [v for v in horizon_config if v != "nuclear"]
    if non_nuclear_values:
        logger.warning(
            "The following conventional technologies are currently not supported as extendable: "
            f"{non_nuclear_values}. They will remain non-extendable.",
        )
