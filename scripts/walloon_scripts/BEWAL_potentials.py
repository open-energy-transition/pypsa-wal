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
            walloon_potentials, index_col=0, dtype={'year': int}
        ).query("year == @planning_horizons")
        print(potentials)
        
        for carrier in potentials.index:
            print(carrier)
            if carrier in n.generators.carrier.unique():
                BEWAL_carrier_idx = (
                    # bus can also be BEWAL low voltage or alike
                    n.generators[n.generators.bus.str.contains("BEWAL")]
                    .query("carrier == @carrier").index
                )
                print(BEWAL_carrier_idx)
                print(n.generators.loc[BEWAL_carrier_idx, "p_nom_max"])
                n.generators.loc[BEWAL_carrier_idx, "p_nom_max"] = potentials.loc[carrier].value
                print(n.generators.loc[BEWAL_carrier_idx, "p_nom_max"])
            else:
                logger.warning(
                    f"{carrier} is currently not a supported or valid technology."
                )
