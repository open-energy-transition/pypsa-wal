import geopandas as gpd
from shapely import wkt
import pandas as pd


def load_buses(buses_fn):
    buses = (
        pd.read_csv(
            buses_fn,
            quotechar="'",
            true_values=["t"],
            false_values=["f"],
            dtype=dict(bus_id="str"),
        )
        .set_index("bus_id")
        .rename(columns=dict(voltage="v_nom"))
    )

    return buses


def load_lines(lines_fn):
    lines = (
        pd.read_csv(
            lines_fn,
            quotechar="'",
            true_values=["t"],
            false_values=["f"],
            dtype=dict(
                line_id="str",
                bus0="str",
                bus1="str",
                underground="bool",
                under_construction="bool",
            ),
        )
        .set_index("line_id")
        .rename(columns=dict(voltage="v_nom", circuits="num_parallel"))
    )

    return lines


def load_links(links_fn):
    links = pd.read_csv(
        links_fn,
        quotechar="'",
        true_values=["t"],
        false_values=["f"],
        dtype=dict(link_id="str", bus0="str", bus1="str", under_construction="bool"),
    ).set_index("link_id")

    return links


def load_converters(converters_fn):
    converters = pd.read_csv(
        converters_fn,
        quotechar="'",
        true_values=["t"],
        false_values=["f"],
        dtype=dict(converter_id="str", bus0="str", bus1="str"),
    ).set_index("converter_id")

    return converters


def load_transformers(transformers_fn):
    transformers = pd.read_csv(
        transformers_fn,
        quotechar="'",
        true_values=["t"],
        false_values=["f"],
        dtype=dict(transformer_id="str", bus0="str", bus1="str"),
    ).set_index("transformer_id")

    return transformers


def map_to_closest_prebuilt_bus(pt, buses_prebuilt, proj_crs="EPSG:3035"):

    # ensure GeoDataFrame with real geometries in a known geographic CRS
    gdf = buses_prebuilt.copy()
    if not isinstance(gdf, gpd.GeoDataFrame) or gdf.geometry.dtype.name != "geometry":
        gdf["geometry"] = gpd.GeoSeries.from_wkt(
            gdf["geometry"].astype(str), crs="EPSG:4326", on_invalid="ignore"
        )
        gdf = gdf.dropna(subset=["geometry"])
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    elif gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    # parse point and project both to a metric CRS
    pt = pt if hasattr(pt, "geom_type") else wkt.loads(str(pt))
    gdf_m = gdf.to_crs(proj_crs)
    pt_m = gpd.GeoSeries([pt], crs=gdf.crs).to_crs(proj_crs).iloc[0]

    # nearest bus id
    return gdf_m.geometry.distance(pt_m).idxmin()


def map_dropped_tyndp_buses_to_closest_prebuilt_bus(
        edges_tyndp, buses_prebuilt, dropped_tyndp_buses
    ):

    for idx in edges_tyndp.index:
        bus0 = edges_tyndp.loc[idx, "bus0"]
        if bus0 in dropped_tyndp_buses.index:
            bus0_geom = dropped_tyndp_buses.loc[bus0, "geometry"]
            prebuilt_bus = map_to_closest_prebuilt_bus(bus0_geom, buses_prebuilt)
            edges_tyndp.loc[idx, "bus0"] = prebuilt_bus
        bus1 = edges_tyndp.loc[idx, "bus1"]
        if bus1 in dropped_tyndp_buses.index:
            bus1_geom = dropped_tyndp_buses.loc[bus1, "geometry"]
            prebuilt_bus = map_to_closest_prebuilt_bus(bus1_geom, buses_prebuilt)
            edges_tyndp.loc[idx, "bus1"] = prebuilt_bus

    return edges_tyndp

def map_remaining_prebuilt_buses_to_closest_tyndp_bus(
        edges_prebuilt, buses_tyndp, dropped_prebuilt_buses
    ):

    for idx in edges_prebuilt.index:
        bus0 = edges_prebuilt.loc[idx, "bus0"]
        if bus0 in dropped_prebuilt_buses.index:
            bus0_geom = dropped_prebuilt_buses.loc[bus0, "geometry"]
            print(bus0, bus0_geom)
            orig_country = dropped_prebuilt_buses.loc[bus0].country
            tyndp_bus = map_to_closest_prebuilt_bus(
                bus0_geom, buses_tyndp.query("country == @orig_country")
            )
            edges_prebuilt.loc[idx, "bus0"] = tyndp_bus
            print(tyndp_bus)
        bus1 = edges_prebuilt.loc[idx, "bus1"]
        if bus1 in dropped_prebuilt_buses.index:
            bus1_geom = dropped_prebuilt_buses.loc[bus1, "geometry"]
            print(bus1, bus1_geom)
            orig_country = dropped_prebuilt_buses.loc[bus1].country
            tyndp_bus = map_to_closest_prebuilt_bus(
                bus1_geom, buses_tyndp.query("country == @orig_country")
            )
            edges_prebuilt.loc[idx, "bus1"] = tyndp_bus
            print(tyndp_bus)
    
    return edges_prebuilt


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "build_tyndp_osm_network",
        )

    countries = snakemake.params.osm_countries

    keep_TYNDP_connections = False

    # BUSES
    buses_prebuilt = load_buses(next(x for x in snakemake.input.input_prebuilt if "buses.csv" in x))
    dropped_prebuilt_buses = buses_prebuilt.query("country not in @countries")
    buses_prebuilt = buses_prebuilt.query("country in @countries")
    buses_tyndp = load_buses(next(x for x in snakemake.input.input_tyndp if "buses.csv" in x))
    dropped_tyndp_buses = buses_tyndp.query("country in @countries")
    buses_tyndp = buses_tyndp.query("country not in @countries")

    buses_mixed = pd.concat([buses_tyndp, buses_prebuilt], axis=0, ignore_index=False)
    buses_mixed.to_csv(next(x for x in snakemake.output if "buses.csv" in x), quotechar="'")

    # LINES
    if keep_TYNDP_connections:
        lines_prebuilt = load_lines(next(x for x in snakemake.input.input_prebuilt if "lines.csv" in x))
        lines_prebuilt = lines_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) and (bus1 in @buses_prebuilt.index)"
        ) # prebuilt lines only in counties 
        lines_tyndp = load_lines(next(x for x in snakemake.input.input_tyndp if "lines.csv" in x))
        lines_tyndp = lines_tyndp.query(
            "(bus0 in @buses_tyndp.index) or (bus1 in @buses_tyndp.index)"
        ) # tyndp lines also between countries ...
        lines_tyndp = map_dropped_tyndp_buses_to_closest_prebuilt_bus(lines_tyndp, buses_prebuilt, buses_tyndp, dropped_tyndp_buses)

        lines_mixed = pd.concat([lines_prebuilt, lines_tyndp], axis=0, ignore_index=False)
        lines_mixed.to_csv(next(x for x in snakemake.output if "lines.csv" in x), quotechar="'")
    else:
        lines_prebuilt = load_lines(next(x for x in snakemake.input.input_prebuilt if "lines.csv" in x))
        lines_prebuilt = lines_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) or (bus1 in @buses_prebuilt.index)"
        ) # prebuilt lines only in counties and to neighbors
        lines_tyndp = load_lines(next(x for x in snakemake.input.input_tyndp if "lines.csv" in x))
        lines_tyndp = lines_tyndp.query(
            "(bus0 in @buses_tyndp.index) and (bus1 in @buses_tyndp.index)"
        ) # tyndp lines only outside of the countries ...
        lines_prebuilt = map_remaining_prebuilt_buses_to_closest_tyndp_bus(lines_prebuilt, buses_tyndp, dropped_prebuilt_buses)

        lines_mixed = pd.concat([lines_prebuilt, lines_tyndp], axis=0, ignore_index=False)
        lines_mixed.to_csv(next(x for x in snakemake.output if "lines.csv" in x), quotechar="'")

    # LINKS
    if keep_TYNDP_connections:
        links_prebuilt = load_links(next(x for x in snakemake.input.input_prebuilt if "links.csv" in x))
        links_prebuilt = links_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) and (bus1 in @buses_prebuilt.index)"
        ) # prebuilt links only in counties 
        links_tyndp = load_links(next(x for x in snakemake.input.input_tyndp if "links.csv" in x))
        links_tyndp = links_tyndp.query(
            "(bus0 in @buses_tyndp.index) or (bus1 in @buses_tyndp.index)"
        ) # tyndp lines also between countries ...
        links_tyndp = map_dropped_tyndp_buses_to_closest_prebuilt_bus(links_tyndp, buses_prebuilt, dropped_tyndp_buses)

        links_mixed = pd.concat([links_prebuilt, links_tyndp], axis=0, ignore_index=False)
        links_mixed.to_csv(next(x for x in snakemake.output if "links.csv" in x), quotechar="'")
    else:
        links_prebuilt = load_links(next(x for x in snakemake.input.input_prebuilt if "links.csv" in x))
        links_prebuilt = links_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) or (bus1 in @buses_prebuilt.index)"
        ) # prebuilt lines only in counties and to neighbors
        links_tyndp = load_links(next(x for x in snakemake.input.input_tyndp if "links.csv" in x))
        links_tyndp = links_tyndp.query(
            "(bus0 in @buses_tyndp.index) and (bus1 in @buses_tyndp.index)"
        ) # tyndp lines only outside of the countries ...
        links_prebuilt = map_remaining_prebuilt_buses_to_closest_tyndp_bus(links_prebuilt, buses_tyndp, dropped_prebuilt_buses)

        links_mixed = pd.concat([links_prebuilt, links_tyndp], axis=0, ignore_index=False)
        links_mixed.to_csv(next(x for x in snakemake.output if "links.csv" in x), quotechar="'")

    # TRANSFORMERS
    if keep_TYNDP_connections:
        trafos_prebuilt = load_transformers(next(x for x in snakemake.input.input_prebuilt if "transformers.csv" in x))
        trafos_prebuilt = trafos_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) and (bus1 in @buses_prebuilt.index)"
        ) # prebuilt links only in counties 
        trafos_tyndp = load_transformers(next(x for x in snakemake.input.input_tyndp if "transformers.csv" in x))
        trafos_tyndp = trafos_tyndp.query(
            "(bus0 in @buses_tyndp.index) or (bus1 in @buses_tyndp.index)"
        ) # tyndp lines also between countries ...
        trafos_tyndp = map_dropped_tyndp_buses_to_closest_prebuilt_bus(trafos_tyndp, buses_prebuilt, dropped_tyndp_buses)

        trafos_mixed = pd.concat([trafos_tyndp, trafos_prebuilt], axis=0, ignore_index=False)
        trafos_mixed.to_csv(next(x for x in snakemake.output if "transformers.csv" in x), quotechar="'")
    else:
        trafos_prebuilt = load_transformers(next(x for x in snakemake.input.input_prebuilt if "transformers.csv" in x))
        trafos_prebuilt = trafos_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) or (bus1 in @buses_prebuilt.index)"
        ) # prebuilt lines only in counties and to neighbors
        trafos_tyndp = load_transformers(next(x for x in snakemake.input.input_tyndp if "transformers.csv" in x))
        trafos_tyndp = trafos_tyndp.query(
            "(bus0 in @buses_tyndp.index) and (bus1 in @buses_tyndp.index)"
        ) # tyndp lines only outside of the countries ...
        trafos_prebuilt = map_remaining_prebuilt_buses_to_closest_tyndp_bus(trafos_prebuilt, buses_tyndp, dropped_prebuilt_buses)

        trafos_mixed = pd.concat([trafos_prebuilt, trafos_tyndp], axis=0, ignore_index=False)
        trafos_mixed.to_csv(next(x for x in snakemake.output if "transformers.csv" in x), quotechar="'")

    # CONVERTERS
    if keep_TYNDP_connections:
        converters_prebuilt = load_converters(next(x for x in snakemake.input.input_prebuilt if "converters.csv" in x))
        converters_prebuilt = converters_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) and (bus1 in @buses_prebuilt.index)"
        ) # prebuilt links only in counties 
        converters_tyndp = load_converters(next(x for x in snakemake.input.input_tyndp if "converters.csv" in x))
        converters_tyndp = converters_tyndp.query(
            "(bus0 in @buses_tyndp.index) or (bus1 in @buses_tyndp.index)"
        ) # tyndp lines also between countries ...
        converters_tyndp = map_dropped_tyndp_buses_to_closest_prebuilt_bus(converters_tyndp, buses_prebuilt, buses_tyndp, dropped_tyndp_buses)

        converters_mixed = pd.concat([converters_tyndp, converters_prebuilt], axis=0, ignore_index=False)
        converters_mixed.to_csv(next(x for x in snakemake.output if "converters.csv" in x), quotechar="'")
    else:
        converters_prebuilt = load_converters(next(x for x in snakemake.input.input_prebuilt if "converters.csv" in x))
        converters_prebuilt = converters_prebuilt.query(
            "(bus0 in @buses_prebuilt.index) or (bus1 in @buses_prebuilt.index)"
        ) # prebuilt lines only in counties and to neighbors
        converters_tyndp = load_converters(next(x for x in snakemake.input.input_tyndp if "converters.csv" in x))
        converters_tyndp = converters_tyndp.query(
            "(bus0 in @buses_tyndp.index) and (bus1 in @buses_tyndp.index)"
        ) # tyndp lines only outside of the countries ...
        converters_prebuilt = map_remaining_prebuilt_buses_to_closest_tyndp_bus(converters_prebuilt, buses_tyndp, dropped_prebuilt_buses)

        converters_mixed = pd.concat([converters_prebuilt, converters_tyndp], axis=0, ignore_index=False)
        converters_mixed.to_csv(next(x for x in snakemake.output if "converters.csv" in x), quotechar="'")

