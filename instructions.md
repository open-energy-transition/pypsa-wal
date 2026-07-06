# PyPSA-Wal — running instructions

Sector-coupled energy system optimisation for Belgium with emphasis on the
Wallonia region (`BEWAL`), built on [PyPSA-Eur](https://github.com/PyPSA/pypsa-eur).

These instructions describe how to install the environment, run the Snakemake
workflow **locally**, and offload the LP solve to the **NIC5 / CÉCI** cluster
using the helper scripts in [`cluster/`](cluster/). The main [`README.md`](README.md)
is unchanged; this file is the operational guide.

The workflow follows the same strategy as
[pypsa-eur_negawatt](https://github.com/PyPSA/pypsa-eur_negawatt): data
retrieval and network preparation run where you have internet; only the
memory-intensive Gurobi solve is optionally delegated to the cluster.

---

## Model overview

| Item | Value |
|------|-------|
| Config file | [`config/config.walloon.yaml`](config/config.walloon.yaml) |
| Run name (`RDIR`) | `walloon-model` |
| Foresight | Myopic (2025 → 2030 → 2040 → 2050) |
| Countries | BE, FR, GB, NL, DE, LU |
| Spatial clustering | Custom 3-node Belgium (`adm` + `custom_busmap_BE`) |
| Temporal resolution | Coarse sector snapshots (`resolution_sector: 3000h`) |
| Solver | Gurobi (`gurobi-default`) |

Walloon-specific settings (nuclear expansion, custom potentials/costs, NTC
constraints, cross-border flows) are documented in [`doc/walloon.rst`](doc/walloon.rst).

### Output paths

Intermediate files live under `resources/walloon-model/`. Final solved networks
and plots are under `results/walloon-model/`. Network files follow the usual
PyPSA-Eur wildcard pattern with empty `opts` and `sector_opts`:

```
results/walloon-model/networks/base_s_adm___2025.nc
results/walloon-model/networks/base_s_adm___2030.nc
…
```

(Three underscores between `adm` and the year — both `opts` and `sector_opts` wildcards are empty strings.)

---

## Prerequisites

- Linux (local or cluster login node)
- [Conda](https://docs.conda.io/) or [Mamba/Micromamba](https://mamba.readthedocs.io/)
- A valid [Gurobi licence](https://www.gurobi.com) (academic licence is sufficient for local runs)
- ~30 GB disk space (data bundle, weather cutout, intermediate files, results)
- For cluster runs: CÉCI SSH access to NIC5 (typically via the `sqvpn` VPN) and scratch space on `$GLOBALSCRATCH`

Observed local footprint for the default Walloon configuration (PR #3, Sep 2025):

| Metric | Value |
|--------|-------|
| Wall-clock time (full workflow) | ~19 min |
| Peak RAM | ~8.2 GB |

---

## Environment setup

Use the **same conda environment name and specification** as pypsa-eur and
pypsa-eur_negawatt: `pypsa-eur`, defined in [`envs/environment.yaml`](envs/environment.yaml).

```bash
cd /path/to/pypsa-wal
conda env create -f envs/environment.yaml    # first time only
conda activate pypsa-eur
```

If the environment already exists (e.g. from pypsa-eur_negawatt), update it:

```bash
conda env update -n pypsa-eur -f envs/environment.yaml --prune
conda activate pypsa-eur
```

Sanity check:

```bash
python -c "import pypsa, snakemake, gurobipy; print('OK')"
```

### Gurobi licence (local)

The workflow is configured to use Gurobi. Obtain a free academic licence at
<https://www.gurobi.com/academia/academic-program-and-licenses/>.

Place the licence file at `~/gurobi.lic` or set:

```bash
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

On NIC5, Gurobi uses a **floating token-server licence**; `./cluster/nic5.sh setup`
copies the module licence to `~/gurobi.lic` automatically (see cluster section below).

---

## Running locally

Activate the environment, then invoke Snakemake with the Walloon config overlay:

```bash
conda activate pypsa-eur
cd /path/to/pypsa-wal

# Dry run — list jobs without executing
snakemake --configfile config/config.walloon.yaml --cores 16 -n

# Full workflow (retrieve data, build networks, solve, post-process, report)
snakemake --configfile config/config.walloon.yaml --cores 16 -call
```

The `-call` flag runs all rules needed for the default `all` target, including
data retrieval from Zenodo/HTTP, network building, four myopic solves, summary
CSVs, and plots.

### Solve chain only

If intermediate files already exist under `resources/walloon-model/`:

```bash
snakemake --configfile config/config.walloon.yaml --cores 16 -call solve_sector_networks
```

### Cluster-equivalent solver settings (local)

Local runs use thread count and memory from
[`config/config.walloon.yaml`](config/config.walloon.yaml) (inherited from
`config.default.yaml`). To match the NIC5 allocation locally:

```bash
snakemake --configfile config/config.walloon.yaml \
  --configfile cluster/config_cluster.yaml \
  --cores 30 -call solve_sector_networks
```

(`cluster/config_cluster.yaml` only overrides `solving.mem_mb`, `solving.cpus`,
and Gurobi `threads`; it does not change model physics.)

### Reducing runtime for testing

The default Walloon config already uses a **coarse** sector time aggregation
(`clustering.temporal.resolution_sector: 3000h`), which keeps solve times short.
For even faster checks during development:

1. Reduce planning horizons in `config/config.walloon.yaml`, e.g. keep only `2050`.
2. Or run a subset of targets explicitly:

   ```bash
   snakemake --configfile config/config.walloon.yaml --cores 4 -call \
     results/walloon-model/networks/base_s_adm___2050.nc
   ```

3. Disable optional retrieval steps in a local override (`config/config.yaml`) if
   data are already cached — see [`config/config.default.yaml`](config/config.default.yaml)
   under `enable:`.

Re-enabling horizons or resolution changes re-triggers upstream build rules.

### Logs

| Location | Contents |
|----------|----------|
| `logs/walloon-model/` | Per-rule Snakemake logs |
| `results/walloon-model/logs/*_solver.log` | Gurobi solver output per horizon |
| `results/walloon-model/logs/*_python.log` | Python-side solve logs |
| `.snakemake/log/` | Master Snakemake run log |

---

## Running the optimisation on NIC5 / CÉCI

The LP solve is the most memory- and CPU-intensive step. The scripts in
[`cluster/`](cluster/) run **only the myopic solve chain** on NIC5, while data
retrieval, network preparation, and post-processing stay on your machine.

### Rationale

- NIC5 **compute nodes have no internet**, so data download and cutout build
  cannot run there. Un-solved networks are **prepared locally**, transferred,
  solved on the cluster, and pulled back.
- Gurobi on NIC5 uses a **token-server licence** (`nic5-login1`); the conda
  `gurobipy` checks out a token automatically after `setup`.
- Snakemake runs on the **login node** (internet for storage providers) and
  submits each rule to Slurm. Compute nodes run only `add_brownfield` and
  `solve_sector_network_myopic`.

Unlike pypsa-eur_negawatt, pypsa-wal has a **single scenario** and a fixed
temporal resolution in config — cluster commands do not take `<scenario>` or
`<resolution>` arguments.

### One-time setup

1. Edit [`cluster/config.sh`](cluster/config.sh): set `REMOTE` (SSH alias),
   `REMOTE_DIR` (scratch path, e.g. `$GLOBALSCRATCH/pypsa-wal`), and review
   Slurm partition/memory defaults.
2. Ensure VPN/SSH access to NIC5 works: `ssh nic5 hostname`.
3. Install the environment on the cluster:

   ```bash
   ./cluster/nic5.sh setup
   ```

   This runs [`cluster/cluster_setup.sh`](cluster/cluster_setup.sh) remotely:
   Miniforge, `pypsa-eur` conda env, Gurobi licence copy, import checks.

### Full cluster workflow

```bash
conda activate pypsa-eur          # local machine
./cluster/nic5.sh run             # prepare → push → solve → wait → pull → postprocess
```

Or step by step:

| Command | What it does |
|---------|--------------|
| `./cluster/nic5.sh prepare` | **Local**: build un-solved networks for all four horizons (`add_existing_baseyear` brownfield for 2025, `prepare_sector_network` bases for 2030–2050) |
| `./cluster/nic5.sh push` | `rsync` code + `resources/` + `data/` (minus multi-GB cutout) + `.snakemake/metadata` to scratch |
| `./cluster/nic5.sh solve` | Launch Slurm orchestrator for the four `solve_sector_network_myopic` jobs |
| `./cluster/nic5.sh stop` | Cancel your Slurm jobs and Snakemake orchestrators |
| `./cluster/nic5.sh status` | `squeue`, orchestrator log tail |
| `./cluster/nic5.sh wait` | Block until the orchestrator finishes |
| `./cluster/nic5.sh pull` | `rsync` solved `results/` and cluster logs back |
| `./cluster/nic5.sh postprocess` | **Local**: `--touch` solve outputs, rebuild summary CSVs and `costs.svg` |
| `./cluster/nic5.sh shell` | Interactive shell in the cluster checkout |

**Progress during `prepare`:** output is streamed to the terminal and logged in
`cluster/logs/prepare.log`. Snakemake also writes to `.snakemake/log/` and
`logs/walloon-model/`. The first local run downloads the data bundle and weather
cutout (~several GB) and can take hours; subsequent runs are incremental.

### Post-processing after pull

`./cluster/nic5.sh run` calls `postprocess` automatically after `pull`. To run it
manually:

```bash
./cluster/nic5.sh postprocess
```

The script:

1. Aligns local brownfield mtimes with pulled solves when those files exist locally.
2. Runs Snakemake **`--touch`** on the four solved `results/walloon-model/networks/*.nc`
   files only (does not re-run Gurobi).
3. Runs summary targets: `results/walloon-model/csvs/costs.csv`,
   `results/walloon-model/graphs/costs.svg`, `results/walloon-model/csvs/cumulative_costs.csv`.

> **Warning — `--touch`**: updates modification times only; it does **not**
> verify file contents. Use only after a successful cluster solve and `pull`.
> Never add `--forcerun` on solve rules.

### Verifying a successful run

After `./cluster/nic5.sh run` (or individual steps):

| Check | What to look for |
|-------|------------------|
| Cluster solve | `cluster/logs/orchestrate.log` ends with `5 of 5 steps (100%) done` or `Complete log` |
| Solved networks | `results/walloon-model/networks/base_s_adm___*.nc` (four files) |
| Gurobi optimality | `grep 'Optimal objective' results/walloon-model/logs/base_s_adm___*_solver.log` |
| Postprocess | `cluster/logs/postprocess.log` completes without errors |
| Local prepare | `cluster/logs/prepare.log` |

Quick commands:

```bash
grep -E 'steps \(100%\) done|Complete log' cluster/logs/orchestrate.log
ls -lh results/walloon-model/networks/base_s_adm___*.nc
grep 'Optimal objective' results/walloon-model/logs/base_s_adm___*_solver.log
ls -lt results/walloon-model/graphs/costs.svg
```

To cancel a run in progress: `./cluster/nic5.sh stop`

### Slurm resource settings

CECI expects allocations to match actual usage — see the
[CECI job efficiency guide](https://support.ceci-hpc.be/doc/SubmittingJobs/JobEfficiency/).

| What | Value | Where |
|------|-------|-------|
| Slurm `--cpus-per-task` (solve) | **30** | `solving.cpus` in [`cluster/config_cluster.yaml`](cluster/config_cluster.yaml) |
| Gurobi threads | **30** | `solving.solver_options.gurobi-default.threads` (same file) |
| Slurm memory (solve) | **32 GB** | `solving.mem_mb` in `cluster/config_cluster.yaml` |
| Partition | **`hmem`** (default) | `SOLVE_PARTITION` in [`cluster/config.sh`](cluster/config.sh) |
| Light rules (`add_brownfield`) | 1 CPU, 16 GB | `--default-resources` in `nic5.sh solve` |

PyPSA-Wal’s default model is **much lighter** than pypsa-eur_negawatt (coarse
3000h sector snapshots, 3-node BE clustering). The `hmem` partition defaults are
conservative; after inspecting `sacct` / `./cluster/nic5.sh status`, consider a
smaller partition and lower `mem_mb` if your jobs use far less than requested.

To change solve CPUs or memory, edit `cluster/config_cluster.yaml` (`solving.cpus`,
`solving.mem_mb`) and keep Gurobi `threads` in sync with `cpus`.

---

## Repository layout (workflow-relevant)

```
.
├── Snakefile                      # Master Snakemake workflow
├── config/
│   ├── config.default.yaml        # PyPSA-Eur defaults
│   └── config.walloon.yaml        # Walloon study configuration
├── cluster/
│   ├── nic5.sh                    # Local ↔ cluster orchestration
│   ├── cluster_setup.sh           # One-time remote env install
│   ├── config.sh                  # SSH paths, Slurm defaults
│   └── config_cluster.yaml        # Solver/memory overrides on NIC5
├── envs/environment.yaml          # Conda env `pypsa-eur`
├── rules/                         # Snakemake rule definitions
├── scripts/                       # Python scripts (incl. walloon_scripts/)
├── data/                          # Static inputs + walloon/ overrides
├── cutouts/                       # Atlite weather cutouts (downloaded)
├── resources/walloon-model/       # Intermediate build artefacts
└── results/walloon-model/         # Solved networks, CSVs, plots
```

---

## Hardware requirements (local)

| Resource | Recommendation |
|----------|----------------|
| RAM | ≥ 16 GB (peak ~8 GB observed for default config) |
| CPU | 16 cores for comfortable build parallelism; 30 threads for Gurobi if using cluster overlay locally |
| Disk | ~30 GB |
| Solve time | Minutes per horizon (default 3000h resolution), vs. hours for high-resolution sector models |

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|-------------------|
| `Directory cannot be locked` | Another Snakemake instance is running, or a stale lock in `.snakemake/locks/` after a crash — stop the other run or remove the lock if no process is active |
| Gurobi `No Gurobi license` | Set `GRB_LICENSE_FILE` or install `~/gurobi.lic` |
| Cluster job pending on `hmem` | Partition busy or allocation too large — try a standard partition and lower `mem_mb` in `config_cluster.yaml` |
| Snakemake rebuilds everything after `pull` | Re-run `./cluster/nic5.sh postprocess` (touch + summaries); do not delete `.snakemake/metadata` locally |
| Missing `config/scenarios.yaml` | Not required unless you set `run.scenarios.enable: true` in config |
| First run hangs on Zenodo cutout download | Symlink `cutouts/europe-2013-sarah3-era5.nc` from `~/.cache/snakemake-pypsa-eur/...` if you already retrieved it for pypsa-eur; or wait for the download to finish |
| `retrieve_osm_boundaries` Overpass 406 errors | Pre-populate `data/osm-boundaries/json/{BA,MD,UA,XK}_adm1.json` from another PyPSA-Eur checkout, or retry later |

---

## Licence

Code inherits the [PyPSA-Eur MIT licence](LICENSES/MIT.txt). Data files retain
their original licences as documented in [`doc/licenses.rst`](doc/licenses.rst).
