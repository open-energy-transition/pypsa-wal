# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: MIT

import pandas as pd
import logging

logger = logging.getLogger(__name__)

def set_line_s_nom_to_ntc(n, ntc_fn):
    """
    Scale interconnection capacities between country pairs to match target NTCs.

    This function reads a CSV of Net Transfer Capacities (NTC) between countries
    and then enforces the target NTC (MW) for each country pair found in both the
    CSV and the network.

    If DC Links exist between the two country bus sets:
        * Treat directions separately
        * For each direction, set the sum of all p_nom over links in that direction
          to the target NTC by uniformly scaling existing `p_nom` values.
          If current sum is zero, distribute the NTC evenly across links.
        * If DC links are found, remove any AC Lines connecting the same pair
           (to avoid double counting parallel AC when a DC representation exists).
    Else if AC Lines exist between the country bus sets (but no DC Links):
         * Uniformly scale their `s_nom` such that the sum of s_nom equals
           the target NTC. If the current sum is zero, distribute NTC evenly.

    Pairs with NTC == 0 are skipped.

    Parameters
    ----------
    n : pypsa.Network
        The network to modify.
    ntc_fn : str or pathlib.Path
        Path to CSV with columns:
        - `source_country_code` (ISO3),
        - `target_country_code` (ISO3),
        - `NTC_2030_MW` (numeric, MW).

    Returns
    -------
    None
        The network `n` is modified in place.
    """

    df = pd.read_csv(ntc_fn)
    
    iso3_to_iso2 = {
        'ALB': 'AL', 'ARM': 'AM', 'AUT': 'AT', 'AZE': 'AZ', 'BEL': 'BE', 'BGR': 'BG',
        'BIH': 'BA', 'BLR': 'BY', 'CHE': 'CH', 'CZE': 'CZ', 'DEU': 'DE', 'DNK': 'DK',
        'ESP': 'ES', 'EST': 'EE', 'FIN': 'FI', 'FRA': 'FR', 'GBR': 'GB', 'GEO': 'GE',
        'GRC': 'GR', 'HRV': 'HR', 'HUN': 'HU', 'IRL': 'IE', 'ITA': 'IT', 'LTU': 'LT',
        'LUX': 'LU', 'LVA': 'LV', 'MDA': 'MD', 'MKD': 'MK', 'MLT': 'MT', 'MNE': 'ME',
        'NLD': 'NL', 'NOR': 'NO', 'POL': 'PL', 'PRT': 'PT', 'ROU': 'RO', 'RUS': 'RU',
        'SRB': 'RS', 'SVK': 'SK', 'SVN': 'SI', 'SWE': 'SE', 'TUR': 'TR', 'UKR': 'UA',
        'XKX': 'XK', 'CYP': 'CY', 'ISR': 'IL', 'DZA': 'DZ', 'MAR': 'MA', 'EGY': 'EG',
        'SAU': 'SA', 'PSE': 'PS', 'LBY': 'LY', 'TUN': 'TN'
    }

    df['source_iso2'] = df['source_country_code'].map(iso3_to_iso2)
    df['target_iso2'] = df['target_country_code'].map(iso3_to_iso2)
    df = df.dropna(subset=['source_iso2', 'target_iso2'])
    pairs = []
    for _, row in df.iterrows():
        pair = tuple(sorted([row['source_iso2'], row['target_iso2']]))
        pairs.append(pair)
    df['pair'] = pairs
    pair_to_ntc = df.groupby('pair')['NTC_2030_MW'].mean()
    focus_countries = list(set(iso3_to_iso2.values()).intersection(set(n.buses.country.unique()))) #['CZ', 'DE', 'GR', 'IT', 'NL', 'PL']
    for pair, ntc in pair_to_ntc.items():
        if ntc == 0:
            continue
        country1, country2 = pair
        if country1 not in focus_countries and country2 not in focus_countries:
            continue
        print(country1, country2)
        if country1 not in focus_countries or country2 not in focus_countries:
            continue

        buses1 = n.buses.query('country == @country1').index
        buses2 = n.buses.query('country == @country2').index
        lines_between = n.lines.query('(bus0 in @buses1 and bus1 in @buses2) or (bus0 in @buses2 and bus1 in @buses1)')
        links_between = n.links.query("carrier == 'DC' and ((bus0 in @buses1 and bus1 in @buses2) or (bus0 in @buses2 and bus1 in @buses1))")

        updated = False
        removed = False
        line_or_link = None
        if not links_between.empty:
            current_total_p_nom_1 = links_between.query("reversed == False")['p_nom'].sum()
            current_total_p_nom_2 = links_between.query("reversed == True")['p_nom'].sum()
            if country1 == "BE" or country2 == "BE":
                print("target (Links)", ntc)
                print("current way 1", current_total_p_nom_1)
                print("current reversed", current_total_p_nom_2)
            if current_total_p_nom_1 > 0:
                scale_factor = ntc / current_total_p_nom_1
                direction = links_between.query("reversed == False").index
                n.links.loc[direction, 'p_nom'] *= scale_factor
            else:
                direction = links_between.query("reversed == False").index
                n.links.loc[direction, 'p_nom'] = ntc / len(direction)
            if current_total_p_nom_2 > 0:
                scale_factor = ntc / current_total_p_nom_2
                direction = links_between.query("reversed == True").index
                n.links.loc[direction, 'p_nom'] *= scale_factor
            else:
                direction = links_between.query("reversed == True").index
                n.links.loc[direction, 'p_nom'] = ntc / len(direction)
            if country1 == "BE" or country2 == "BE":
                print("updated", n.links.loc[links_between.index].query("reversed == False")['p_nom'].sum())
                print("updated", n.links.loc[links_between.index].query("reversed == True")['p_nom'].sum())
                print(n.links.loc[links_between.index][["bus0", "bus1", "p_min_pu", "p_max_pu", "reversed", "p_nom"]])
            updated = True
            line_or_link = "Link"
        if (updated) and (not lines_between.empty):
            removed = True
            removed_lines = lines_between.index
            n.remove("Line", removed_lines)
            # lines_between should be empty now
            lines_between = n.lines.query('(bus0 in @buses1 and bus1 in @buses2) or (bus0 in @buses2 and bus1 in @buses1)')
        if (not updated) and (not lines_between.empty):
            current_total_s_nom = lines_between['s_nom'].sum()
            if country1 == "BE" or country2 == "BE":
                print("target (Lines)", ntc)
                print("current", current_total_s_nom)
            if current_total_s_nom > 0:
                scale_factor = ntc / current_total_s_nom
                n.lines.loc[lines_between.index, 's_nom'] *= scale_factor
            else:
                n.lines.loc[lines_between.index, 's_nom'] = ntc / len(lines_between)
            if country1 == "BE" or country2 == "BE":
                print("updated", n.lines.loc[lines_between.index, 's_nom'].sum())
            updated = True
            line_or_link = "Line"
        if updated:
            logger.info(f"Set {line_or_link} capacity to a total of {ntc} MW for interconnections between {country1} and {country2}")
        else:
            logger.warning(f"No interconnections found between {country1} and {country2}")
        if removed:
            logger.info(f"Removed lines {removed_lines}, because there was already a valid link connection {links_between.index}.")
