#!/usr/bin/env bash
# _run.sh  [LA pipeline — WSL / Linux]
#
# Activates the pdal_env conda environment then runs the requested stage.
#
# Usage:
#   bash _run.sh 00              -> 00_compute_extent.py
#   bash _run.sh 01              -> 01_clip_footprints.py
#   bash _run.sh 02              -> 02_extract_classes.py  (all classes)
#   bash _run.sh 02 building     -> building class only
#   bash _run.sh 02 building 0.1 -> building at 0.1 m override

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_BASE="/mnt/c/Users/Glytc/miniconda3"

# Activate pdal_env from Windows miniconda via WSL interop
eval "$("$CONDA_BASE/bin/conda" shell.bash hook 2>/dev/null)" || {
    # Fallback: source conda directly if hook fails
    source "$CONDA_BASE/etc/profile.d/conda.sh"
}
conda activate pdal_env

case "${1:-}" in
    00) python "$SCRIPT_DIR/00_compute_extent.py" ;;
    01) python "$SCRIPT_DIR/01_clip_footprints.py" ;;
    02) python "$SCRIPT_DIR/02_extract_classes.py" "${2:-}" "${3:-}" ;;
    dl) bash "$SCRIPT_DIR/00_download_data.sh" ;;
    *)
        echo "Usage: bash _run.sh [dl|00|01|02] [class] [spacing]"
        echo "  dl  — download LiDAR tiles + footprints"
        echo "  00  — compute tile extent + Blender shift"
        echo "  01  — clip + reproject footprints"
        echo "  02  — extract per-class point clouds"
        exit 1
        ;;
esac
