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

    print(extendable_nuclear_nodes)
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
