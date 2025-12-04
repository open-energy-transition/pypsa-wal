# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def update_BEWAL_potentials(n, planning_horizons, walloon_potentials=None):
    if walloon_potentials == None:
        return

    potentials = pd.read_csv(
        walloon_potentials, dtype={"year": int, "value": str}
    ).query("year == @planning_horizons")

    if "technology" not in potentials.columns:
        potentials = potentials.rename(columns={potentials.columns[0]: "technology"})

    for _, row in potentials.iterrows():
        attr = row["parameter"]
        carrier = row["technology"]
        unit = str(row.get("unit", ""))
        raw_value = row.get("value")
        bus_value = row.get("bus")
        bus = (
            "BEWAL" if pd.isna(bus_value) else str(bus_value)
        )  # default bus is "BEWAL" if not specified

        if isinstance(raw_value, str):
            if raw_value.strip().lower() == "inf":
                potential = np.inf
            elif raw_value in ["TRUE", "true", "True"]:
                potential = True
            elif raw_value in ["FALSE", "false", "False"]:
                potential = False
            else:
                potential = float(raw_value)
        else:
            potential = float(raw_value)

        if np.isfinite(potential) and ("GW" in unit or "GWh" in unit):
            potential = potential * 1000  # convert to MW or MWh

        logger_msg_success = (
            f"Overwriting exogenously given potentials for {carrier} on bus {bus}."
        )
        logger_msg_failure = (
            f"{carrier} is currently not a supported or valid technology."
        )
        if carrier == "offwind":
            carriers_to_update = ["offwind-ac", "offwind-dc", "offwind-float"]
        elif carrier in n.generators.carrier.unique() and carrier not in [
            "solid biomass",
            "biogas",
        ]:
            carriers_to_update = [carrier]
        else:
            carriers_to_update = []

        if carriers_to_update:
            region_carrier_idx = []
            for tech in carriers_to_update:
                bus_mask = n.generators.bus == bus
                carrier_mask = n.generators.carrier == tech
                idx = n.generators[bus_mask & carrier_mask].index

                gen_name = f"{bus} 0 {tech}-{planning_horizons}"
                if gen_name in n.generators.index:
                    idx = pd.Index([gen_name])

                if not idx.empty:
                    region_carrier_idx.extend(idx.tolist())

            if len(region_carrier_idx) == 0:
                continue
            if region_carrier_idx:
                allowed = {"p_nom", "p_nom_max", "p_nom_min"}
                assert attr in allowed, (
                    f"Unsupported attr: {attr!r}; expected one of {', '.join(sorted(allowed))}"
                )
                logger.info(logger_msg_success)
                n.generators.loc[region_carrier_idx, attr] = potential
            continue

        if carrier in ["solid biomass", "biogas"]:
            logger.info(logger_msg_success)
            if carrier == "biogas":
                unsustainable_idx = f"BEWAL {carrier} unsustainable"
            else:
                unsustainable_idx = f"BEWAL unsustainable {carrier}"

            allowed = "p_nom"
            assert attr == allowed, f"Unsupported attr: {attr!r}; expected {allowed!r}"
            pypsa_eur_potential = n.generators.loc[f"BEWAL {carrier}", attr]
            if pypsa_eur_potential <= potential and carrier == "solid biomass":
                if "unsustainable biomass limit" in n.global_constraints.index:
                    n.generators.loc[unsustainable_idx, [attr, "e_sum_max"]] = (
                        potential - pypsa_eur_potential
                    )
                    limit = n.global_constraints.loc[
                        "unsustainable biomass limit", "constant"
                    ]
                    n.global_constraints.loc[
                        "unsustainable biomass limit", "constant"
                    ] = limit - pypsa_eur_potential + potential
            elif carrier == "solid biomass":
                if "unsustainable biomass limit" in n.global_constraints.index:
                    limit = n.global_constraints.loc[
                        "unsustainable biomass limit", "constant"
                    ]
                    n.global_constraints.loc[
                        "unsustainable biomass limit", "constant"
                    ] = limit - n.generators.loc[unsustainable_idx, attr]
                if unsustainable_idx in n.generators.index:
                    n.generators.loc[unsustainable_idx, [attr, "e_sum_max"]] = 0
            n.generators.loc[f"BEWAL {carrier}", [attr, "e_sum_max"]] = potential
            # what about ["BEWAL solid biomass transported", "BEWAL unsustainable solid biomass transported"] ?
            # what about ["BEWAL solid biomass transported", "BEWAL unsustainable solid biomass transported"] ?
        elif carrier == "solid biomass import":
            # remove all solid biomass imports except the one for BEWAL
            # and set the import potential to the one given for BEWAL
            logger.info(logger_msg_success)
            biomass_imports = n.stores.query("carrier == @carrier")

            allowed = "e_nom"
            assert attr == allowed, f"Unsupported attr: {attr!r}; expected {allowed!r}"
            n.stores.loc[
                biomass_imports.index,
                ["e_nom_min", attr, "e_nom_max", "e_initial"],
            ] = potential

            biomass_imports = biomass_imports.bus.values
            biomass_imports = n.links.query("bus0 in @biomass_imports").index
            drop_non_BEWAL_imports = [
                link for link in biomass_imports if "BEWAL" not in link
            ]
            n.remove("Link", drop_non_BEWAL_imports)
        elif carrier == "solid biomass transported":
            allowed = "e_sum_max"
            assert attr == allowed, f"Unsupported attr: {attr!r}; expected {allowed!r}"
            logger.info(logger_msg_success)

            sustainable_idx = "BEWAL solid biomass transported"
            unsustainable_idx = "BEWAL unsustainable solid biomass transported"

            if sustainable_idx not in n.generators.index:
                logger.warning(
                    "No BEWAL solid biomass transported generators found; "
                    "skipping transported biomass potential overwrite.",
                )
                continue

            # Cap the annual imported biomass energy (pellets) to the provided potential.
            # Enforce the limit on the sustainable generator and disable
            # the unsustainable copy so that the total transported energy cannot exceed
            # the given GWh/an value.
            n.generators.loc[sustainable_idx, attr] = potential
            if unsustainable_idx in n.generators.index:
                n.generators.loc[unsustainable_idx, ["p_nom", attr]] = 0
        if carrier == "CCGT":
            allowed = {"p_nom", "p_nom_extendable", "p_nom_min", "p_nom_max"}
            assert attr in allowed, (
                f"Unsupported attr: {attr!r}; expected one of {', '.join(sorted(allowed))}"
            )

            link_name = f"{bus} {carrier}-{planning_horizons}"
            if "el" in unit:
                potential = potential / n.links.loc[link_name, "efficiency"]
            n.links.loc[link_name, attr] = potential
        if carrier == "nuclear":
            allowed = {"p_nom", "p_nom_extendable", "p_nom_min", "p_nom_max"}
            assert attr in allowed, (
                f"Unsupported attr: {attr!r}; expected one of {', '.join(sorted(allowed))}"
            )

            link_name = f"{bus} {carrier}-{planning_horizons}"
            if "el" in unit:
                potential = potential / n.links.loc[link_name, "efficiency"]
            n.links.loc[link_name, attr] = potential
        else:
            logger.warning(logger_msg_failure)
