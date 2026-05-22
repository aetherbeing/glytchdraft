#!/usr/bin/env bash
# 00_download_data.sh
#
# Downloads the LA hero LiDAR tiles (USGS 3DEP CA_LosAngeles_2016) and
# LA County building footprints into /mnt/t7/la/data_raw/.
#
# Hero area: Downtown LA / Bunker Hill (Walt Disney Concert Hall, Grand Park,
# Pershing Square) — four quarter-tiles from the 1836 grid cell.
#
# Run from WSL:
#   bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/00_download_data.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAZ_DIR="/mnt/t7/la/data_raw/laz"
SHP_DIR="/mnt/t7/la/data_raw/shp"
GEOJSON_DIR="/mnt/t7/la/data_raw/geojson"
BASE_URL="https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/USGS_LPC_CA_LosAngeles_2016_LAS_2018/laz"

# Four quarter-tiles covering downtown LA core (1836 grid cell, ~26 MB each compressed)
TILES=(
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836a_LAS_2018.laz"
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836c_LAS_2018.laz"
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836d_LAS_2018.laz"
)

echo "=== Downloading LA 3DEP LiDAR tiles ==="
mkdir -p "$LAZ_DIR"
for tile in "${TILES[@]}"; do
    dest="$LAZ_DIR/$tile"
    if [[ -f "$dest" ]]; then
        echo "  already exists, skipping: $tile"
    else
        echo "  downloading: $tile"
        wget -q --show-progress -O "$dest" "$BASE_URL/$tile"
        echo "  done: $(du -sh "$dest" | cut -f1)"
    fi
done

echo ""
echo "=== Downloading LA County Building Outlines ==="
mkdir -p "$SHP_DIR" "$GEOJSON_DIR"

FOOTPRINT_DEST="$GEOJSON_DIR/la_county_building_outlines_4326.geojson"

if [[ -f "$FOOTPRINT_DEST" && -s "$FOOTPRINT_DEST" ]]; then
    echo "  already exists: $(du -sh "$FOOTPRINT_DEST" | cut -f1)"
else
    echo "  querying hero-tile area only (ESRI FeatureServer → OSM Overpass fallback)..."
    python "$SCRIPT_DIR/00_download_footprints.py"
fi

echo ""
echo "=== Download complete ==="
echo "Hero LAZ (pipeline default):  $LAZ_DIR/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"
echo "Footprints:                   $FOOTPRINT_DEST"
echo ""
echo "Next: run the pipeline"
echo "  bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/_run.sh 00"
echo "  bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/_run.sh 01"
echo "  bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/_run.sh 02"
