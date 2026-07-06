#!/bin/bash
# SPDX-License-Identifier: MIT
###############################################################################
# nic5.sh  -  Run the PyPSA-Wal optimisation on the NIC5/CECI cluster
#
# Strategy: heavy LP solving runs on NIC5 (hmem + Gurobi), everything else
# stays local. Un-solved networks are prepared locally, transferred to the
# cluster, the myopic solve chain runs there, and solved networks are pulled
# back for post-processing.
#
# pypsa-wal uses a single scenario (config/config.walloon.yaml, run name
# "walloon-model"). Temporal resolution is fixed in that config
# (clustering.temporal.resolution_sector: 3000h) — there is no sector_opts
# resolution switch like in pypsa-eur_negawatt.
#
#   ./cluster/nic5.sh setup       # one-time: install env on the cluster
#   ./cluster/nic5.sh run         # full test: prepare+push+solve+wait+pull+postprocess
#
# or step by step:
#   ./cluster/nic5.sh prepare     # LOCAL: build un-solved solve inputs
#   ./cluster/nic5.sh push        # rsync code + inputs to the cluster
#   ./cluster/nic5.sh solve       # submit solve chain on Slurm
#   ./cluster/nic5.sh status      # squeue + tail logs
#   ./cluster/nic5.sh wait        # block until jobs finish
#   ./cluster/nic5.sh pull        # rsync solved results back
#   ./cluster/nic5.sh postprocess # LOCAL: touch solve outputs, rebuild summaries
###############################################################################
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
# shellcheck source=config.sh
source "$HERE/config.sh"
JOBFILE="$HERE/.last_jobs"
mkdir -p "$HERE/logs"

msg()  { printf '\033[1;34m[nic5]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[nic5] WARNING:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[nic5] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# shellcheck disable=SC2086
rssh() { ssh $SSH_OPTS "$REMOTE" "$@"; }
# shellcheck disable=SC2086
rssync() { rsync -e "ssh $SSH_OPTS" "$@"; }

snakemake_local() {
    # shellcheck disable=SC2086
    ( cd "$REPO" && $LOCAL_RUN snakemake --configfile "$CONFIGFILE" "$@" )
}

cluster_cpus() {
    awk '/^solving:/{s=1} s && /^  cpus:/{print $NF; exit}' "$HERE/config_cluster.yaml"
}

network_basename() {
    echo "base_s_${CLUSTERS}_${OPTS}_${SECTOR_OPTS}"
}

solved_targets() {
    local y base
    base=$(network_basename)
    for y in $HORIZONS; do
        echo "results/${RUN_NAME}/networks/${base}_${y}.nc"
    done
}

brownfield_targets() {
    local y base
    base=$(network_basename)
    for y in $HORIZONS; do
        echo "resources/${RUN_NAME}/networks/${base}_${y}_brownfield.nc"
    done
}

prepare_targets() {
    local y first base
    first=$(echo "$HORIZONS" | awk '{print $1}')
    base=$(network_basename)
    echo "resources/${RUN_NAME}/networks/${base}_${first}_brownfield.nc"
    for y in $HORIZONS; do
        [ "$y" = "$first" ] && continue
        echo "resources/${RUN_NAME}/networks/${base}_${y}.nc"
    done
}

postprocess_targets() {
    echo "results/${RUN_NAME}/csvs/costs.csv"
    echo "results/${RUN_NAME}/graphs/costs.svg"
    echo "results/${RUN_NAME}/csvs/cumulative_costs.csv"
}

verify_run_success() {
    local y t ok=0 base log
    base=$(network_basename)
    log="$HERE/logs/orchestrate.log"
    msg "Verifying run for '$RUN_NAME'"
    if [ -f "$log" ] && grep -qE 'steps \(100%\) done|Complete log' "$log"; then
        msg "  cluster orchestrator: OK ($log)"
    else
        warn "  cluster orchestrator: CHECK $log"
        ok=1
    fi
    for y in $HORIZONS; do
        t="results/${RUN_NAME}/networks/${base}_${y}.nc"
        if [ -f "$REPO/$t" ]; then
            msg "  solved network $y: OK ($(du -h "$REPO/$t" | awk '{print $1}'))"
        else
            warn "  solved network $y: MISSING ($t)"
            ok=1
        fi
        t="results/${RUN_NAME}/logs/${base}_${y}_solver.log"
        if [ -f "$REPO/$t" ] && grep -q 'Optimal objective' "$REPO/$t"; then
            msg "  solver log $y: OK (optimal)"
        elif [ -f "$REPO/$t" ]; then
            warn "  solver log $y: CHECK $t (no 'Optimal objective' line)"
            ok=1
        else
            warn "  solver log $y: MISSING ($t)"
            ok=1
        fi
    done
    log="$HERE/logs/postprocess.log"
    if [ -f "$log" ] && grep -qE 'steps \(100%\) done|Nothing to be done|Complete log' "$log"; then
        msg "  postprocess: OK ($log)"
    else
        warn "  postprocess: not completed — run: $0 postprocess"
        ok=1
    fi
    return "$ok"
}

sync_brownfield_mtimestamps() {
    local y base bf sol
    base=$(network_basename)
    for y in $HORIZONS; do
        bf="resources/${RUN_NAME}/networks/${base}_${y}_brownfield.nc"
        sol="results/${RUN_NAME}/networks/${base}_${y}.nc"
        if [ -f "$REPO/$bf" ] && [ -f "$REPO/$sol" ]; then
            touch -r "$REPO/$sol" "$REPO/$bf"
        fi
    done
}

cmd_prepare() {
    local targets log
    log="$HERE/logs/prepare.log"
    targets=$(prepare_targets | tr '\n' ' ')
    msg "Preparing un-solved solve inputs locally ($LOCAL_CORES cores)"
    msg "  config: $CONFIGFILE"
    msg "  targets: $targets"
    msg "  log: $log  (also: $REPO/.snakemake/log/ and $REPO/logs/${RUN_NAME}/)"
    snakemake_local \
        --cores "$LOCAL_CORES" \
        --rerun-triggers mtime \
        --printshellcmds \
        -- $targets 2>&1 | tee "$log"
    msg "Local preparation complete."
}

cmd_push() {
    msg "Syncing repo + inputs to ${REMOTE}:${REMOTE_DIR}"
    rssh "mkdir -p '$REMOTE_DIR'"
    rssync -arh --no-g \
        --exclude '.git' --exclude '.pixi' \
        --exclude 'results' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude 'cluster/logs' --exclude 'cutouts' --exclude 'data/cutout' \
        "$REPO/" "${REMOTE}:${REMOTE_DIR}/"
    if [ -d "$REPO/.snakemake/metadata" ]; then
        rssh "mkdir -p '$REMOTE_DIR/.snakemake'"
        rssync -arh --no-g "$REPO/.snakemake/metadata" "${REMOTE}:${REMOTE_DIR}/.snakemake/"
    fi
    msg "Push complete."
}

REMOTE_ENV='source $HOME/miniforge3/etc/profile.d/conda.sh && conda activate '"$ENV_NAME"' && unset PYTHONPATH && export GRB_LICENSE_FILE=$HOME/gurobi.lic'

cmd_solve() {
    local solve_cpus targets log pidf pid
    solve_cpus=$(cluster_cpus)
    [ -n "$solve_cpus" ] || die "solving.cpus not set in cluster/config_cluster.yaml"
    : > "$JOBFILE"
    msg "Launching Slurm orchestrator on the login node (cpus=$solve_cpus)"
    targets=$(solved_targets | tr '\n' ' ')
    log="cluster/logs/orchestrate.log"
    pidf="cluster/logs/orchestrate.pid"
    rssh "cd '$REMOTE_DIR' && $REMOTE_ENV && mkdir -p cluster/logs && \
        setsid bash -c \"snakemake --configfile cluster/config_cluster.yaml \
            --configfile $CONFIGFILE \
            --executor slurm --jobs $MAX_SLURM_JOBS \
            --rerun-triggers mtime --keep-going --printshellcmds \
            --default-resources slurm_partition=$SOLVE_PARTITION runtime=$SOLVE_RUNTIME mem_mb=$DEFAULT_MEM_MB slurm_account=ceci \
            --set-resources solve_sector_network_myopic:cpus_per_task=$solve_cpus \
            --set-threads solve_sector_network_myopic=$solve_cpus \
            --set-resources add_brownfield:cpus_per_task=1 \
            -- $targets </dev/null >'$log' 2>&1 & echo \\\$! >'$pidf'\" </dev/null >/dev/null 2>&1"
    sleep 2
    pid=$(rssh "cat '$REMOTE_DIR/$pidf' 2>/dev/null" | tr -d '[:space:]')
    echo "walloon ${pid:-unknown}" >> "$JOBFILE"
    msg "  orchestrator pid ${pid:-unknown} (log: $log)"
    msg "Track with: $0 status"
}

cmd_stop() {
    msg "Cancelling Slurm jobs and orchestrators on $REMOTE"
    rssh "scancel -u \$(whoami) 2>/dev/null; pkill -f 'bin/snakemake --configfile' 2>/dev/null || true"
    msg "Stop signalled."
}

status_job_usage() {
    rssh 'bash -s' <<'REMOTE'
set -uo pipefail
running=$(squeue --me -h -t RUNNING -o "%i|%N|%j|%C|%m" 2>/dev/null || true)
if [ -z "$running" ]; then
    echo "(no running Slurm jobs)"
    exit 0
fi
while IFS='|' read -r jobid node name alloc_cpus alloc_mem; do
    [ -n "$jobid" ] || continue
    echo "--- job $jobid on $node (alloc: ${alloc_cpus} CPUs, ${alloc_mem}) ---"
    short=${name:0:40}
    [ "$short" != "$name" ] && short="${short}..."
    echo "    name: $short"
done <<< "$running"
REMOTE
}

cmd_status() {
    msg "Slurm queue on $REMOTE (squeue --me):"
    rssh "squeue --me --format='%.18i %.10P %.26j %.8T %.10M %R'" 2>/dev/null
    echo
    msg "Live jobs:"
    status_job_usage
    [ -f "$JOBFILE" ] || return 0
    local _ job_pid
    while read -r _ job_pid; do
        echo
        if rssh "kill -0 $job_pid" 2>/dev/null; then
            msg "--- orchestrator (pid $job_pid: RUNNING) ---"
        else
            msg "--- orchestrator (pid $job_pid: finished) ---"
        fi
        rssh "grep -vE 'Lmod|Try: |module\(s\)|Python/3.7.4' '$REMOTE_DIR/cluster/logs/orchestrate.log' 2>/dev/null | tail -n 12 || echo '(no log yet)'"
    done < "$JOBFILE"
}

cmd_wait() {
    [ -f "$JOBFILE" ] || die "no orchestrators recorded ($JOBFILE missing)"
    msg "Waiting for orchestrators to finish..."
    local _ job_pid
    while true; do
        local alive=0
        while read -r _ job_pid; do
            rssh "kill -0 $job_pid" 2>/dev/null && alive=$((alive+1))
        done < "$JOBFILE"
        [ "$alive" -eq 0 ] && break
        printf '\r[nic5] %s orchestrator(s) still running... %s' "$alive" "$(date +%H:%M:%S)"
        sleep 60
    done
    printf '\n'
    if rssh "grep -qE 'Nothing to be done|steps \(100%\) done|Complete log' '$REMOTE_DIR/cluster/logs/orchestrate.log'" 2>/dev/null; then
        msg "Orchestrator: OK"
    else
        warn "Orchestrator: CHECK LOG (cluster/logs/orchestrate.log) — may have errors"
    fi
}

cmd_pull() {
    msg "Pulling results + logs from cluster"
    mkdir -p "$REPO/results" "$HERE/logs"
    rssync -arh --no-g --info=progress2 \
        "${REMOTE}:${REMOTE_DIR}/results/" "$REPO/results/" \
        || msg "(no results dir yet)"
    rssync -arh --no-g \
        "${REMOTE}:${REMOTE_DIR}/cluster/logs/" "$HERE/logs/" || true
    msg "Pull complete. Solved networks are in results/${RUN_NAME}/networks/."
}

cmd_postprocess() {
    local touch_targets targets log
    warn "postprocess runs LOCALLY after pull."
    warn "Step 1 uses Snakemake --touch on solved networks only (does NOT re-run Gurobi)."
    local t
    for t in $(solved_targets); do
        [ -f "$REPO/$t" ] || die "missing $t — run './cluster/nic5.sh pull' (and solve) first"
    done
    sync_brownfield_mtimestamps
    touch_targets=$(solved_targets | tr '\n' ' ')
    targets=$(postprocess_targets | tr '\n' ' ')
    log="$HERE/logs/postprocess.log"

    msg "Touching solved networks (Snakemake --touch)"
    snakemake_local \
        --cores 1 \
        --rerun-triggers mtime \
        --touch \
        -- $touch_targets 2>&1 | tee "$log"

    msg "Running summary plots and CSVs"
    snakemake_local \
        --cores "$LOCAL_CORES" \
        --rerun-triggers mtime \
        --printshellcmds \
        -- $targets 2>&1 | tee -a "$log"

    msg "Post-processing complete (log: $log)."
}

cmd_setup() {
    msg "One-time cluster setup on $REMOTE"
    rssh "mkdir -p '$REMOTE_DIR/cluster'"
    rssync -arh --no-g "$HERE/cluster_setup.sh" "${REMOTE}:${REMOTE_DIR}/cluster/cluster_setup.sh"
    rssync -arh --no-g "$REPO/envs/environment.yaml" "${REMOTE}:${REMOTE_DIR}/envs/environment.yaml"
    rssh "bash '$REMOTE_DIR/cluster/cluster_setup.sh'"
    msg "Setup finished."
}

cmd_run() {
    cmd_prepare
    cmd_push
    cmd_solve
    cmd_wait
    cmd_pull
    cmd_postprocess
    verify_run_success || warn "Run finished with verification warnings (see messages above)."
}

cmd_shell() { ssh $SSH_OPTS -t "$REMOTE" "cd '$REMOTE_DIR'; exec bash -l"; }

case "${1:-}" in
    setup)       shift; cmd_setup "$@";;
    prepare)     shift; cmd_prepare "$@";;
    push)        shift; cmd_push "$@";;
    solve)       shift; cmd_solve "$@";;
    stop)        shift; cmd_stop "$@";;
    status)      shift; cmd_status "$@";;
    wait)        shift; cmd_wait "$@";;
    pull)        shift; cmd_pull "$@";;
    postprocess) shift; cmd_postprocess "$@";;
    run)         shift; cmd_run "$@";;
    shell)       shift; cmd_shell "$@";;
    *) cat <<EOF
Usage: $0 <command> [args...]
  setup         one-time: install conda env + Gurobi licence on the cluster
  prepare       LOCAL: build un-solved solve inputs (myopic chain)
  push          rsync code + inputs to the cluster (scratch)
  solve         submit the myopic solve chain on Slurm
  stop          cancel Slurm jobs and orchestrators on the cluster
  status        show queue and orchestrator logs
  wait          block until the submitted orchestrator finishes
  pull          rsync solved results back into ./results
  postprocess   LOCAL (after pull): --touch solve outputs, rebuild summaries/plots
  run           prepare + push + solve + wait + pull + postprocess
  shell         open an interactive shell in the cluster repo

  Examples:
    $0 run
    $0 solve && $0 wait && $0 pull && $0 postprocess
EOF
       exit 1;;
esac
