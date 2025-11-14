# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

import pandas as pd

DEFAULT_AGG_LIMITS = Path("data/agg_p_nom_minmax.csv")

logger = logging.getLogger(__name__)


def add_BEWAL_nuclear(
    n,
    planning_horizon,
    extendable_nuclear_nodes: dict = {2040: ["BEWAL"], 2050: ["BEWAL"]},
    agg_limit_file: str | None = None,
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
    agg_limit_file : str, optional
        Path to aggregated min/max capacities (defaults to ``data/agg_p_nom_minmax.csv``).
    """

    if planning_horizon in extendable_nuclear_nodes.keys():
        extendable_nuclear_links = [
            f"{bus} nuclear-2025" for bus in extendable_nuclear_nodes[planning_horizon]
        ]
        link_missing = [
            link for link in extendable_nuclear_links if link not in n.links.index
        ]
        extendable_nuclear_links = list(
            set(extendable_nuclear_links) - set(link_missing)
        )

        if link_missing:
            logger.warning(
                "Requested nuclear link '%s' not found; unable to update costs.",
                link_missing,
            )

        if extendable_nuclear_links:
            n.links.loc[extendable_nuclear_links, "p_nom_extendable"] = True

    # Enforce minimum nuclear capacity if agg limits are available
    limit_path = Path(agg_limit_file) if agg_limit_file else DEFAULT_AGG_LIMITS
    if not limit_path.exists():
        logger.debug(
            "Aggregated capacity limit file '%s' not found; skipping nuclear p_nom_min update.",
            limit_path,
        )
        return

    # CSV has two header rows: first horizon, second min/max
    try:
        agg = pd.read_csv(limit_path, index_col=[0, 1], header=[0, 1])
    except ValueError as exc:
        logger.warning(
            "Failed to read aggregated capacity limits from %s: %s", limit_path, exc
        )
        return
    horizon = str(planning_horizon)
    if horizon not in agg.columns.get_level_values(0):
        logger.debug(
            "No aggregated nuclear limits for %s in %s; skipping.",
            planning_horizon,
            limit_path,
        )
        return

    agg_year = agg[horizon]
    if "nuclear-all" not in agg_year.index.get_level_values(1):
        logger.debug("No 'nuclear-all' rows found in aggregated limits; skipping.")
        return

    limits = agg_year.xs("nuclear-all", level="carrier")
    if "min" not in limits.columns:
        logger.debug(
            "Aggregated limit file missing 'min' column for %s; skipping.", horizon
        )
        return

    # Map bus names to ISO country codes (Belgium splits)
    bus_country = n.buses.country.copy()
    fallback = pd.Series(n.buses.index, index=n.buses.index)
    bus_country = bus_country.where(bus_country.notna(), fallback)
    belgian = {"BEWAL": "BE", "BEBRU": "BE", "BEVLG": "BE"}
    bus_country.update(belgian)

    links = n.links[n.links.carrier == "nuclear"].copy()
    if links.empty:
        return

    links["country"] = links.bus1.map(bus_country)
    # existing fleet (non-extendable) counts towards target (in MW_e)
    existing = (
        links.query("~p_nom_extendable")
        .assign(p_nom_e=lambda df: df.p_nom * df.efficiency)
        .groupby("country")
        .p_nom_e.sum()
    )

    # Extendable links we can enforce min on
    extendable = links.query("p_nom_extendable").copy()
    if extendable.empty:
        return

    extendable["p_nom_e"] = extendable.p_nom * extendable.efficiency

    for country, limit in limits["min"].dropna().items():
        target = float(limit)
        existing_cap = existing.get(country, 0.0)
        shortfall = max(0.0, target - existing_cap)
        if shortfall <= 0.0:
            continue
        country_links = extendable[extendable.country == country]
        if country_links.empty:
            continue
        # simple: assign entire shortfall to the first extendable link (there is only one per country)
        idx = country_links.index[0]
        eff = country_links.loc[idx, "efficiency"]
        if pd.isna(eff) or eff <= 0:
            eff = 1.0
        current_min = n.links.at[idx, "p_nom_min"]
        if pd.isna(current_min):
            current_min = 0.0
        required_min = shortfall / eff
        n.links.at[idx, "p_nom_min"] = max(current_min, required_min)
