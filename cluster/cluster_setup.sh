#!/bin/bash
# SPDX-License-Identifier: MIT
###############################################################################
# cluster_setup.sh  -  One-time environment setup on NIC5 (run ON the cluster).
#
# Invoked by `cluster/nic5.sh setup`. Installs Miniforge in $HOME, creates the
# `pypsa-eur` conda environment from envs/environment.yaml (the SAME environment
# name/spec used locally and by pypsa-eur_negawatt), and wires up the Gurobi
# token-server licence so the conda gurobipy can check out a token from any
# compute node.
#
# Adapted from pypsa-eur_negawatt/cluster/cluster_setup.sh. UNTESTED for
# pypsa-wal -- verify GUROBI_MODULE_LIC below still matches the cluster before
# running this.
###############################################################################
set -euo pipefail

ENV_NAME="pypsa-eur"
MINIFORGE="$HOME/miniforge3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
GUROBI_MODULE_LIC="/opt/cecisw/arch/easybuild/2023b/software/Gurobi/13.0.0-GCCcore-13.2.0/gurobi.lic"

echo "=== [1/4] Miniforge ==="
if [ ! -x "$MINIFORGE/bin/conda" ]; then
    tmp="$(mktemp -d)"
    curl -fsSL -o "$tmp/mf.sh" \
        "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
    bash "$tmp/mf.sh" -b -p "$MINIFORGE"
    rm -rf "$tmp"
else
    echo "Miniforge already present."
fi
source "$MINIFORGE/etc/profile.d/conda.sh"

echo "=== [2/4] conda environment '$ENV_NAME' ==="
if conda env list | grep -qE "^\s*${ENV_NAME}\s"; then
    echo "Env exists; updating from environment.yaml..."
    conda env update -n "$ENV_NAME" -f "$REPO/envs/environment.yaml" --prune
else
    conda env create -n "$ENV_NAME" -f "$REPO/envs/environment.yaml"
fi

echo "=== [3/4] Gurobi licence (token server) ==="
if [ -r "$GUROBI_MODULE_LIC" ]; then
    cp -f "$GUROBI_MODULE_LIC" "$HOME/gurobi.lic"
    echo "Copied $GUROBI_MODULE_LIC -> $HOME/gurobi.lic"
else
    echo "WARNING: module licence not readable at $GUROBI_MODULE_LIC"
    echo "         load the Gurobi module and copy its gurobi.lic to ~/gurobi.lic manually."
fi

echo "=== [4/4] sanity checks ==="
export GRB_LICENSE_FILE="$HOME/gurobi.lic"
unset PYTHONPATH || true
conda activate "$ENV_NAME"
python - <<'PY'
import importlib.metadata as m
for p in ("pypsa", "linopy", "snakemake", "gurobipy"):
    try:
        print(f"  {p:10s} {m.version(p)}")
    except Exception as e:
        print(f"  {p:10s} MISSING ({e})")
try:
    import gurobipy as gp
    env = gp.Env()           # checks out a token from the cluster's licence server
    env.dispose()
    print("  gurobi licence : OK (token checkout succeeded)")
except Exception as e:
    print(f"  gurobi licence : FAILED -> {e}")
PY
echo "=== setup done ==="
