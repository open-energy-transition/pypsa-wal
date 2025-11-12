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
            unit = str(potentials.loc[carrier].unit)
            value = potentials.loc[carrier].value
            if "GW" in unit and "GWh" not in unit:
                potential = value * 1000
            elif "GWh" in unit:
                potential = value * 1000  # convert GWh to MWh
            else:
                potential = value

            logger_msg_success = f"Overwriting exogenously given potentials for {carrier} in BEWAL."
            logger_msg_failure =  f"{carrier} is currently not a supported or valid technology."
            if carrier in n.generators.carrier.unique() and carrier not in ["solid biomass", "biogas"]:
                logger.info(logger_msg_success)

                BEWAL_carrier_idx = (
                    # bus can also be BEWAL low voltage or alike
                    n.generators[n.generators.bus.str.contains("BEWAL")]
                    .query("carrier == @carrier").index
                )
                n.generators.loc[BEWAL_carrier_idx, "p_nom_max"] = potential

            elif carrier in ["solid biomass", "biogas"]:
                logger.info(logger_msg_success)
                if carrier == "biogas":
                    unsustainable_idx = f"BEWAL {carrier} unsustainable"
                else:
                    unsustainable_idx = f"BEWAL unsustainable {carrier}"

                pypsa_eur_potential = n.generators.loc[f"BEWAL {carrier}", "p_nom"]
                if pypsa_eur_potential <= potential:
                    n.generators.loc[unsustainable_idx, ["p_nom", "e_sum_max"]] = potential - pypsa_eur_potential
                    if carrier == "solid biomass":
                        limit = n.global_constraints.loc["unsustainable biomass limit", "constant"]
                        n.global_constraints.loc["unsustainable biomass limit", "constant"] = (
                            limit - pypsa_eur_potential + potential
                        )
                else:
                    if carrier == "solid biomass":
                        limit = n.global_constraints.loc["unsustainable biomass limit", "constant"]
                        n.global_constraints.loc["unsustainable biomass limit", "constant"] = (
                            limit - n.generators.loc[unsustainable_idx, "p_nom"]
                        )
                        limit = n.global_constraints.loc["biomass limit", "constant"]
                        n.global_constraints.loc["biomass limit", "constant"] = (
                            limit - pypsa_eur_potential + potential
                        )
                    n.generators.loc[f"BEWAL {carrier}", ["p_nom", "e_sum_max"]] = potential
                    n.generators.loc[unsustainable_idx, ["p_nom", "e_sum_max"]] = 0
                # what about ["BEWAL solid biomass transported", "BEWAL unsustainable solid biomass transported"] ?
                # what about ["BEWAL solid biomass transported", "BEWAL unsustainable solid biomass transported"] ?
            elif carrier == 'solid biomass import':
                # remove all solid biomass imports except the one for BEWAL
                # and set the import potential to the one given for BEWAL
                logger.info(logger_msg_success)
                biomass_imports = n.stores.query("carrier == @carrier")

                n.stores.loc[biomass_imports.index, ["e_nom_min", "e_nom", "e_nom_max", "e_initial"]] = potential

                biomass_imports = biomass_imports.bus.values
                biomass_imports = n.links.query("bus0 in @biomass_imports").index
                drop_non_BEWAL_imports = [link for link in biomass_imports if "BEWAL" not in link]
                n.remove("Link", drop_non_BEWAL_imports)
            elif carrier == "solid biomass transported":
                logger.info(logger_msg_success)
                transported_generators = [
                    "BEWAL solid biomass transported",
                    "BEWAL unsustainable solid biomass transported",
                ]
                present_generators = [idx for idx in transported_generators if idx in n.generators.index]

                if not present_generators:
                    logger.warning(
                        "No BEWAL solid biomass transported generators found; "
                        "skipping transported biomass potential overwrite.",
                    )
                    continue

                energy_caps = (
                    n.generators.loc[present_generators, "e_sum_max"]
                    .fillna(0)
                )

                total_existing = energy_caps.sum()
                if total_existing <= 0:
                    # default to allocating all energy to the sustainable generator
                    allocation = pd.Series(0, index=present_generators, dtype=float)
                    allocation.iloc[0] = potential
                else:
                    allocation = energy_caps / total_existing * potential

                n.generators.loc[present_generators, "e_sum_max"] = allocation.values
            else:
                logger.warning(logger_msg_failure)
