# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import logging

logger = logging.getLogger(__name__)

def add_BEWAL_nuclear(n, walloon_nuclear_config, planning_horizon):
    """
    Update the BEWAL nuclear link in the network to be extendable if 'nuclear' is
    listed for the given planning horizon.

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
    """

    if 'nuclear' in walloon_nuclear_config.get(planning_horizon, []):
        n.links.loc["BEWAL nuclear-2025", "p_nom_extendable"] = True
    non_nuclear_values = [v for v in walloon_nuclear_config.get(planning_horizon, []) if v != "nuclear"]
    if non_nuclear_values:
        logger.warning(
            "The following conventional technologies are currently not supported as extendable: "
            f"{non_nuclear_values}. They will remain non-extendable.",
        )
