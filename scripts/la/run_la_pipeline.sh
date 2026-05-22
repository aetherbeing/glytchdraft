#!/usr/bin/env bash
# run_la_pipeline.sh
#
# Comprehensive WSL runner for the LA hero-tile pipeline.
# Handles conda activation, data download, and all pipeline stages.
#
# Usage:
#   bash run_la_pipeline.sh            # full pipeline (download + 00 + 01 + 02)
#   bash run_la_pipeline.sh --skip-dl  # skip download, run stages only
#   bash run_la_pipeline.sh 00         # single stage
#   bash run_la_pipeline.sh 01
#   bash run_la_pipeline.sh 02
#   bash run_la_pipeline.sh 02 building
#   bash run_la_pipeline.sh 02 building 0.1

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_BASE="$HOME/miniconda3"
LOG_DIR="/mnt/t7/la/data_processed/hero_tile/notes"
LOG_FILE="$LOG_DIR/pipeline_run.log"

# ── helpers ──────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

hr() { echo "──────────────────────────────────────────────────────" | tee -a "$LOG_FILE"; }

run_stage() {
    local label="$1"; shift
    hr
    log "STAGE $label: starting"
    local t0=$SECONDS
    python "$SCRIPT_DIR/${label}_"*.py "$@" 2>&1 | tee -a "$LOG_FILE"
    local exit_code=${PIPESTATUS[0]}
    local elapsed=$(( SECONDS - t0 ))
    if [[ $exit_code -ne 0 ]]; then
        log "STAGE $label: FAILED (exit $exit_code) after ${elapsed}s"
        exit $exit_code
    fi
    log "STAGE $label: done in $(printf '%dm %02ds' $((elapsed/60)) $((elapsed%60)))"
}

# ── conda activation ──────────────────────────────────────────────────────────

activate_conda() {
    if [[ -f "$CONDA_BASE/bin/conda" ]]; then
        eval "$("$CONDA_BASE/bin/conda" shell.bash hook 2>/dev/null)" \
            || source "$CONDA_BASE/etc/profile.d/conda.sh"
        conda activate pdal_env
        log "conda: pdal_env activated (python: $(which python))"
    elif [[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
        source "$CONDA_BASE/etc/profile.d/conda.sh"
        conda activate pdal_env
        log "conda: pdal_env activated via profile.d"
    else
        log "WARN: miniconda not found at $CONDA_BASE"
        log "      Continuing with system python — PDAL/GDAL may fail."
    fi
}

# ── pre-flight checks ─────────────────────────────────────────────────────────

preflight() {
    local ok=1

    # T7 drive
    if ! mountpoint -q /mnt/t7 2>/dev/null && [[ ! -d /mnt/t7 ]]; then
        log "ERROR: /mnt/t7 is not mounted. Plug in the T7 drive."
        ok=0
    fi

    # Hero LAZ
    local laz="/mnt/t7/la/data_raw/laz/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"
    if [[ ! -f "$laz" ]]; then
        log "WARN: hero LAZ not found — will download."
        NEED_DOWNLOAD=1
    else
        log "hero LAZ: found ($(du -sh "$laz" | cut -f1))"
        NEED_DOWNLOAD=0
    fi

    # Footprints
    local fp="/mnt/t7/la/data_raw/geojson/la_county_building_outlines_4326.geojson"
    if [[ ! -f "$fp" ]]; then
        log "WARN: footprints not found — will download."
        NEED_DOWNLOAD=1
    else
        log "footprints: found ($(du -sh "$fp" | cut -f1))"
    fi

    # Python packages
    for pkg in pdal osgeo; do
        python -c "import $pkg" 2>/dev/null \
            && log "python: $pkg OK" \
            || { log "ERROR: python package '$pkg' not importable — activate pdal_env first."; ok=0; }
    done

    [[ $ok -eq 1 ]] || exit 1
}

# ── main ──────────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

hr
log "GlytchDraft — LA hero-tile pipeline"
log "script dir : $SCRIPT_DIR"
log "output root: /mnt/t7/la/data_processed/hero_tile/"
log "log        : $LOG_FILE"
hr

activate_conda
preflight

SKIP_DL=0
SINGLE_STAGE=""

# Parse args
case "${1:-}" in
    --skip-dl)
        SKIP_DL=1
        shift
        ;;
    00|01|02)
        SINGLE_STAGE="${1}"
        shift
        ;;
esac

# Single-stage shortcut
if [[ -n "$SINGLE_STAGE" ]]; then
    case "$SINGLE_STAGE" in
        00) run_stage "00" ;;
        01) run_stage "01" ;;
        02) run_stage "02" "${1:-}" "${2:-}" ;;
    esac
    hr
    log "done."
    exit 0
fi

# Full pipeline
if [[ $SKIP_DL -eq 0 && ${NEED_DOWNLOAD:-0} -eq 1 ]]; then
    hr
    log "DOWNLOAD: fetching LiDAR tiles + footprints"
    bash "$SCRIPT_DIR/00_download_data.sh" 2>&1 | tee -a "$LOG_FILE"
    log "DOWNLOAD: complete"
fi

run_stage "00"
run_stage "01"
run_stage "02"

hr
log "Pipeline complete."
log ""
log "Outputs:"
log "  /mnt/t7/la/data_processed/hero_tile/notes/hero_tile_extent.txt"
log "  /mnt/t7/la/data_processed/hero_tile/notes/hero_tile.shift.txt"
log "  /mnt/t7/la/data_processed/hero_tile/footprints/hero_tile_footprints_32611.geojson"
log "  /mnt/t7/la/data_processed/hero_tile/pointcloud/hero_tile_ground_32611_1m.ply"
log "  /mnt/t7/la/data_processed/hero_tile/pointcloud/hero_tile_building_32611_0p25m.ply"
log "  /mnt/t7/la/data_processed/hero_tile/pointcloud/hero_tile_water_32611_1m.ply"
log ""
log "Next: open Blender, import PLYs + GeoJSON, apply shift from hero_tile.shift.txt"
hr
