import pandas as pd

AG_LOAD_CARRIERS = {"agriculture electricity", "agriculture machinery electric"}


def _compute_electric_loads_and_prices(n):
    """Return (prices, total_loads) aligned on common bus columns."""

    elec_cost_buses = n.buses.query("carrier in ['low voltage']").index
    prices = n.buses_t["marginal_price"][elec_cost_buses]

    # All loads connected to low-voltage buses
    elec_load = n.loads.query("bus in @elec_cost_buses").bus.values
    elec_load = list(
        set(elec_load).intersection(
            set(n.loads_t.p_set.rename(columns=n.loads.bus.to_dict()).columns)
        )
    )

    # Time-varying loads
    loads = (
        n.loads_t.p_set.rename(columns=n.loads.bus.to_dict())[elec_load]
        .multiply(n.snapshot_weightings.generators, axis=0)
        .copy()
    )
    loads.columns.name = "Load"

    # Constant loads
    const_loads = n.loads.p_set.rename(index=n.loads.bus.to_dict())
    const_loads = const_loads.groupby(level=0).sum()
    const_loads = (
        pd.DataFrame(
            {bus: const_loads[bus] for bus in const_loads.index}, index=n.snapshots
        )
        .rename(columns=n.loads.bus.to_dict())[elec_load]
        .multiply(n.snapshot_weightings.generators, axis=0)
    )
    const_loads.columns.name = "Load"

    # Electric heating demand
    heat_power_tech = [c for c in n.links.carrier.unique() if "heat" in c]
    heat_loads = n.links.query("carrier in @heat_power_tech").index
    heat_loads = (
        n.links_t.p0[heat_loads]
        .T.groupby(n.links.bus0)
        .sum()
        .T.multiply(n.snapshot_weightings.generators, axis=0)
        .rename(columns=n.links.bus0.to_dict())
    )
    heat_loads.columns.name = "Load"

    # Electric EV demand
    EV_tech = [c for c in n.links.carrier.unique() if "EV charger" in c]
    EV_loads = n.links.query("carrier in @EV_tech").index
    EV_loads = (
        n.links_t.p0[EV_loads]
        .multiply(n.snapshot_weightings.generators, axis=0)
        .rename(columns=n.links.bus0.to_dict())
    )
    EV_loads.columns.name = "Load"

    # Home battery demand
    hb_tech = [c for c in n.links.carrier.unique() if "battery charger" in c]
    hb_idx = n.links.query("carrier in @hb_tech").index
    hb_loads = (
        n.links_t.p0[hb_idx]
        .multiply(n.snapshot_weightings.generators, axis=0)
        .rename(columns=n.links.loc[hb_idx, "bus0"].to_dict())
    )
    # collapse duplicate columns (same bus) to avoid reindex errors
    if not hb_loads.empty and hb_loads.columns.duplicated().any():
        hb_loads = hb_loads.T.groupby(level=0).sum().T
    hb_loads.columns.name = "Load"

    # Agriculture electric loads (if present)
    ag_idx = n.loads.index[n.loads.carrier.isin(AG_LOAD_CARRIERS)]
    ag_loads = pd.DataFrame(index=n.snapshots, columns=[])
    ag_cols = []
    if len(ag_idx):
        ag_buses = n.loads.loc[ag_idx, "bus"].unique()
        # Check if any ag_buses is already included in elec_load
        # Only if missing then calculate ag_loads
        missing_buses = [b for b in ag_buses if b not in elec_cost_buses]
        if missing_buses:
            # Time-varying part on missing buses
            p_set_bus = n.loads_t.p_set.rename(columns=n.loads.bus.to_dict())
            ag_ts_buses = [b for b in missing_buses if b in p_set_bus.columns]
            if ag_ts_buses:
                ag_ts = p_set_bus[ag_ts_buses].multiply(
                    n.snapshot_weightings.generators, axis=0
                )
                ag_loads = ag_loads.join(ag_ts, how="outer")

            # Constant part for missing buses (p_set on loads table)
            const_bus = n.loads.p_set.rename(index=n.loads.bus.to_dict())
            const_bus = const_bus.groupby(level=0).sum()
            ag_const_buses = [b for b in missing_buses if b in const_bus.index]
            if ag_const_buses:
                const_df = pd.DataFrame(
                    {bus: const_bus[bus] for bus in ag_const_buses}, index=n.snapshots
                ).multiply(n.snapshot_weightings.generators, axis=0)
                ag_loads = ag_loads.join(const_df, how="outer")

            ag_loads = ag_loads.fillna(0)
            ag_cols = ag_loads.columns

    # Align all load components on the union of bus columns
    all_cols = sorted(set(elec_load) | set(ag_cols))
    reindex_kw = dict(columns=all_cols, fill_value=0)

    total_loads = (
        loads.reindex(**reindex_kw)
        .add(const_loads.reindex(**reindex_kw), fill_value=0)
        .add(heat_loads.reindex(**reindex_kw), fill_value=0)
        .add(hb_loads.reindex(**reindex_kw), fill_value=0)
        .add(EV_loads.reindex(**reindex_kw), fill_value=0)
        .add(ag_loads.reindex(**reindex_kw), fill_value=0)
    )

    # Keep only buses where we have a marginal price
    cols = [c for c in total_loads.columns if c in prices.columns]
    total_loads = total_loads[cols]
    prices = prices[cols]

    return prices, total_loads


def get_electriciy_price_weighted(n):
    """Compute average electricity price weighted by electric load over time."""
    prices, total_loads = _compute_electric_loads_and_prices(n)
    if total_loads.empty:
        return 0.0, pd.Series(dtype=float)

    denom = total_loads.sum(axis=1).replace(0, pd.NA)
    prices_weighted = (prices * total_loads).sum(axis=1) / denom

    weighted_mean_price = prices_weighted.mean()

    return weighted_mean_price, prices_weighted


def get_household_bills(n, households_path="data/walloon/households.csv"):
    """
    Compute electricity cost per household per snapshot and aggregated over the horizon.

    Returns
    -------
    bills_ts : DataFrame
        Snapshot-resolved bills per country; includes a 'weighted_average' column.
    bills_agg : Series
        Horizon-aggregated bill per country (total cost / households).
    """

    prices, total_loads = _compute_electric_loads_and_prices(n)
    if total_loads.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    bus_country = n.buses.country.reindex(total_loads.columns).dropna()
    if bus_country.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    prices = prices[bus_country.index]
    total_loads = total_loads[bus_country.index]

    costs_country_ts = (prices * total_loads).groupby(bus_country, axis=1).sum()

    households = (
        pd.read_csv(households_path)
        .set_index("Country")["Households (thousands)"]
        .mul(1e3)
    )
    households = households.reindex(costs_country_ts.columns).dropna()
    if households.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    costs_country_ts = costs_country_ts[households.index]
    bills_ts = costs_country_ts.divide(households, axis=1)

    # Aggregate over the horizon: total cost per country / households
    costs_country_agg = costs_country_ts.sum()
    bills_agg = costs_country_agg / households

    return bills_ts, bills_agg


if __name__ == "__main__":
    if "snakemake" in globals():
        import pypsa

        network = pypsa.Network(snakemake.input.network)
        households_path = (
            snakemake.input.households
            if "households" in snakemake.input.keys()
            else "data/walloon/households.csv"
        )

        mean_price, price_ts = get_electriciy_price_weighted(network)
        bills_ts, bills_agg = get_household_bills(network, households_path)

        price_ts.to_csv(snakemake.output.weighted_prices)
        bills_ts.to_csv(snakemake.output.household_bills_ts)
        bills_agg.to_csv(snakemake.output.household_bills_agg)
    else:
        raise SystemExit("This script is intended to be run via Snakemake.")
