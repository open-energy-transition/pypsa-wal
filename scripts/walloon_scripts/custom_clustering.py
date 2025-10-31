# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

import logging
import geopandas as gpd
from shapely.geometry import Point

logger = logging.getLogger(__name__)

def ppl_by_subregion(n, ppl, country='BE', gdf_path="data/walloon/be.json"):
    """
    powerplants in the given country will be reassigned to subregions specified in gdf_path (json).
    """
    
    country_idx = n.buses.query("country==@country").index
    n.buses.loc[country_idx, "country"] = country_idx

    gdf = gpd.read_file(gdf_path)
    filtered_ppl = ppl[ppl.Country == country]
    for i in filtered_ppl.index:
        try:
            country_subregion_id = gdf[gdf.geometry.contains(Point(ppl.iloc[i].lon, ppl.iloc[i].lat))]['id'].values[0]
            logger.info(
                f"reassigning powerplant {ppl.at[i, "Name"]} in country {ppl.at[i, 'Country']}"
                f" to the specific region {country_subregion_id}."
            )
            ppl.at[i, 'Country'] = country_subregion_id
        except:
            pass
    return n, ppl
