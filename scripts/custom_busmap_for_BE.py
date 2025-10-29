# SPDX-FileCopyrightText: Open Energy Transition gGmbH and contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Creates a custom busmap for Belgium with 3 resulting buses that map to the administrative zones of
- Flanders: BEVLG
- Walloon: BEWAL
- Bruxelles: BEBRU

Outputs
-------

- ``resources/base_s_adm.csv``

"""

import pypsa
import pandas as pd
import geopandas as gpd
import geopandas as gpd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

def map_buses_to_be_regions(n, be_regions):

    bus_pts = gpd.GeoDataFrame(
        n.buses.index.to_series().rename("Bus"),
        geometry=gpd.points_from_xy(n.buses["x"], n.buses["y"]),
        crs="EPSG:4326"  # adjust if bus coords are not lon/lat WGS84
    ).set_index("Bus")

    # created this to avoid warning, but it doesn't seem to help:
    # geometry is in a geographic CRS. Results from 'distance' are likely incorrect.
    # Use 'GeoSeries.to_crs()' to re-project geometries to a projected CRS before this operation.
    be_regions = be_regions.to_crs(bus_pts.crs)

    bus_pts_and_regions = gpd.sjoin(
        bus_pts,
        be_regions[["id", "geometry"]],
        how="left",
        predicate="within"
    )

    # map any remaining unmapped buses in BE to nearest shape/region
    missing_be = bus_pts_and_regions["id"].isna() & (n.buses["country"] == 'BE')
    if missing_be.any():

        nearest = gpd.sjoin_nearest(
            bus_pts.loc[missing_be],
            be_regions[["id", "geometry"]],
            how="left",
            distance_col="dist_m",
        ).drop(columns=["index_right"])

        bus_pts_and_regions.loc[nearest.index, "id"] = nearest["id"].values

    bru_geom = be_regions.query("id == 'BEBRU'").geometry.iloc[0]
    bus_pts["dist_to_bru"] = bus_pts.geometry.distance(bru_geom)

    closest_buses = bus_pts["dist_to_bru"].sort_values(ascending=True)
    closest_buses = bus_pts.loc[bus_pts["dist_to_bru"] < 0.1].geometry

    bus_pts_and_regions.loc[closest_buses.index, 'id'] = 'BEBRU'
    bus_pts_and_regions["region_id"] = (
        bus_pts_and_regions["id"].fillna(n.buses["country"]).astype("string")
    )
    
    return bus_pts_and_regions["region_id"]


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("custom_busmap_for_BE")

    n = pypsa.Network(snakemake.input.network)
    be_regions = gpd.read_file(snakemake.input.be_shapefile)

    busmap = map_buses_to_be_regions(n, be_regions)

    busmap.to_csv(snakemake.output[0])