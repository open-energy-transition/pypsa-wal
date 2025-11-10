# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import pandas as pd
import logging

logger = logging.getLogger(__name__)


def update_BEWAL_potentials(n, planning_horizons, walloon_potentials=None):

    if walloon_potentials is not None:
        potentials=pd.read_csv(
            walloon_potentials, index_col=0,
            dtype={'year': int, 'value': float}
        ).query("year == @planning_horizons")
        
        for carrier in potentials.index:
            if carrier in n.generators.carrier.unique():
                BEWAL_carrier_idx = (
                    # bus can also be BEWAL low voltage or alike
                    n.generators[n.generators.bus.str.contains("BEWAL")]
                    .query("carrier == @carrier").index
                )
                n.generators.loc[BEWAL_carrier_idx, "p_nom_max"] = potentials.loc[carrier].value
            elif carrier == 'solid biomass import':
                # remove all solid biomass imports except the one for BEWAL
                # and set the import potential to the one given for BEWAL
                biomass_imports = n.stores.query("carrier == @carrier")

                if "GW" in potentials.loc[carrier].unit:
                    e_nom = potentials.loc[carrier].value * 1000
                else:
                    e_nom = potentials.loc[carrier].value
                for col in ["e_nom_min", "e_nom", "e_nom_max", "e_initial"]:
                    n.stores.loc[biomass_imports.index, col] = e_nom

                biomass_imports = biomass_imports.bus.values
                biomass_imports = n.links.query("bus0 in @biomass_imports").index
                drop_non_BEWAL_imports = [link for link in biomass_imports if "BEWAL" not in link]
                n.remove("Link", drop_non_BEWAL_imports)
            else:
                logger.warning(
                    f"{carrier} is currently not a supported or valid technology."
                )
