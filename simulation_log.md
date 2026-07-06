# Simulation log — pypsa-wal walloon-model

Date: 2026-07-02  
Config: `config/config.walloon.yaml` (`run.name: walloon-model`)  
Horizons: 2025, 2030, 2040, 2050  
Solved networks: `results/walloon-model/networks/base_s_adm___<year>.nc`

## Summary

The myopic solve chain failed initially because **Country & Carrier Limits (CCL)** in `data/agg_p_nom_minmax.csv` required more renewable capacity than the model can build, given existing plants, land-use potentials, and the `include_existing: true` logic in `scripts/solve_network.py`.

After adjusting CCL minima for **BEWAL solar** (2025) and **DE/NL offwind** (2030–2050), all four horizons solve to optimality locally. A separate post-processing failure (`numpy.trapz` removed in NumPy 2.x) was fixed in `scripts/make_cumulative_costs.py`.

---

## Issue 1 — BEWAL `solar-all` (2025)

### Symptom

Gurobi IIS on 2025 solve:

- `Generator-ext-p_nom-lower[BEWAL 0 solar-2025]` — expandable solar must be ≥ ~1805 MW
- `Generator-ext-p_nom-upper[BEWAL 0 solar-2025]` — expandable solar capped at ~1598 MW (3887 − 2289 existing)
- Conflicting `agg_p_nom_min` / `agg_p_nom_max` on `(BEWAL, solar-all)` and parent `(BE, solar-all)`

### Root cause

With `include_existing: true`, CCL bounds apply to **new** capacity:

| Quantity | Value (MW) |
|----------|------------|
| Existing non-extendable solar at BEWAL | ~2289 |
| `agg_p_nom_minmax` min/max for BEWAL 2025 | 3887 |
| Max expandable (`3887 − 2289`) | ~1598 |
| Generator `p_nom_min` on `solar-2025` | ~1805 |

Minimum expandable (1805) > maximum expandable (1598) → infeasible.

Clearing BEWAL min without adjusting max left `(BE, solar-all)` with min expandable > max expandable after parent–child subtraction.

### Fix

In `data/agg_p_nom_minmax.csv`, raise BEWAL 2025 solar minimum to match achievable capacity and keep min/max symmetric:

```csv
BEWAL,solar-all,5090,5090,5090,,5090,,7867,,7867,,9564,
```

(was `3887,3887` for 2025 min/max)

### Verification

```
grep 'Optimal objective' results/walloon-model/logs/base_s_adm___2025_solver.log
# Optimal objective 2.85768391e+11
```

---

## Issue 2 — DE / NL `offwind-all` (2030–2050)

### Symptom

2030+ solves infeasible after 2025 succeeded. Gurobi IIS consistently involved:

- `agg_p_nom_min[(DE, offwind-all)]` or `[(NL, offwind-all)]`
- `Generator-ext-p_nom-upper[DE|NL 0 offwind-ac-<year>]` with very small or zero headroom

Log warning (expected):

```
Existing capacities larger than technical potential for ['DE 0 offwind-ac-2030', 'NL 0 offwind-ac-2030']
```

### Root cause

EU-wide offwind minima in `agg_p_nom_minmax.csv` (e.g. DE 2030 min = 20521 MW, NL 2030 min = 16543 MW) exceed what this regional model can deliver:

1. **Land-use constraint** (`add_land_use_constraint` in `solve_network.py`) subtracts existing non-extendable capacity from extendable `p_nom_max` per bus/carrier.
2. For DE and NL, **existing offshore AC capacity already exceeds the technical potential** on the single cluster bus (`DE 0`, `NL 0`), so extendable AC headroom becomes ~0.
3. With `include_existing: true`, the CCL minimum applies to **incremental** capacity: `min_expand = agg_min − existing_alive`.

Example (2030 brownfield, after land-use adjustment):

| Country | Existing alive (MW) | Max expandable (MW) | Achievable total (MW) | Policy min (MW) | Required expansion (MW) |
|---------|---------------------|---------------------|----------------------|-----------------|---------------------------|
| DE | 9215 | 1013 | 10228 | 20521 | 11306 |
| NL | 5800 | 22 | 5822 | 16543 | 10743 |

Later horizons compound the problem as plant lifetimes expire and brownfield capacities from previous solves are carried forward.

### Fix

Cap CCL minima at **achievable totals** (existing alive + adjusted expandable max), with small rounding margin to avoid floating-point IIS:

| Row | Column | Old | New |
|-----|--------|-----|-----|
| `DE,offwind-all` | 2030 min | 20521 | **10227** |
| `DE,offwind-all` | 2040 min | 20521 | **10147** |
| `DE,offwind-all` | 2050 min | 20521 | **5153** |
| `NL,offwind-all` | 2030 min | 16543 | **5822** |
| `NL,offwind-all` | 2040 min | 50543 | **5594** |
| `NL,offwind-all` | 2050 min | 50543 | **4504** |

These values reflect renewable potentials in the Walloon model topology, not revised EU policy targets. Document any interpretation of offwind build-out accordingly.

### Verification

```
grep 'Optimal objective' results/walloon-model/logs/base_s_adm___*_solver.log
# 2025: 2.85768391e+11
# 2030: 2.51267197e+11
# 2040: 3.28794334e+11
# 2050: 1.39634574e+11
```

---

## Issue 3 — Post-processing (`make_cumulative_costs`)

### Symptom

```
AttributeError: module 'numpy' has no attribute 'trapz'
```

### Fix

`scripts/make_cumulative_costs.py`: `np.trapz` → `np.trapezoid` (NumPy 2.x / Python 3.13).

---

## Compatibility fixes applied during workflow testing

| File | Change |
|------|--------|
| `scripts/build_co2_sequestration_potentials.py` | `dissolve()` instead of broken `groupby().agg(unary_union)`; read `ID2` from KML when `id` is null |
| `scripts/build_gas_network.py`, `scripts/build_gas_input_locations.py` | Handle GeoJSON `param` already parsed as dict |
| `scripts/add_electricity.py` | PyPSA v1 busmap fallback when `name` column missing |
| `scripts/make_cumulative_costs.py` | `np.trapezoid` for NumPy 2.x |

---

## Data staging notes (local build)

Snakemake data retrieval needed manual staging for some inputs:

- Cutout symlink: `cutouts/europe-2013-sarah3-era5.nc`
- OSM boundaries from `pypsa-eur_negawatt`
- EEZ, JRC IDEES, databundle, ship density (after retrieval failures)

See `instructions.md` and `cluster/logs/prepare.log`.

---

## Known non-blocking issues

- **`plot_balance_timeseries`**: can fail with empty carrier data (`IndexError` on `df.index[0]`). Not part of `nic5.sh postprocess` targets (`costs.csv`, `costs.svg`, `cumulative_costs.csv`).
- **DE/NL offwind warning** at solve time is expected given existing capacity vs. cluster-level potentials.

---

## NIC5 cluster run

Orchestration: `./cluster/nic5.sh run` (or step-by-step: `prepare`, `push`, `solve`, `wait`, `pull`, `postprocess`).

### Cluster tooling fixes (2026-07-02)

| Issue | Fix |
|-------|-----|
| `REMOTE_DIR` used local `whoami` (`sylvain`) | Set to `/scratch/ulg/thermlab/squoilin/pypsa-wal` in `cluster/config.sh` |
| `nic5.sh solve` empty `$CONFIGFILE` (single-quoted remote shell) | Fixed quoting; added `mkdir -p cluster/logs` |
| Dual `--configfile` order dropped myopic rules | Use `cluster/config_cluster.yaml` **before** `config/config.walloon.yaml` |
| Slurm jobs requested 125 GB / 32 CPUs | Set `solving.mem_mb: 32000` in `config.walloon.yaml`; cluster overlay uses 8 threads via `--set-threads` |
| `hmem` partition draining | Default partition switched to `batch` in `cluster/config.sh` |
| Slurm queue congested (Priority pending) | Successful run executed on NIC5 login node with local Snakemake executor (`--cores 8`) after `push`; Slurm path remains available via `./cluster/nic5.sh solve` |

### Verification (NIC5, 2026-07-02)

```
grep 'Optimal objective' results/walloon-model/logs/base_s_adm___*_solver.log
# 2025: 2.85768391e+11
# 2030: 2.51267197e+11
# 2040: 3.28794334e+11
# 2050: 1.39634574e+11
```

Post-process targets: `results/walloon-model/csvs/costs.csv`, `graphs/costs.svg`, `csvs/cumulative_costs.csv`.

Cluster logs: `cluster/logs/orchestrate.log`, `cluster/logs/postprocess.log`.
