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

# LA County Building Outlines — LA GeoHub / ESRI Open Data
# Delivered as EPSG:4326 GeoJSON. ~2.4M features county-wide.
FOOTPRINT_URL="https://opendata.arcgis.com/api/v3/datasets/eb8b0f1d36274c6f9d7bc7c3abf01f97_0/downloads/data?format=geojson&spatialRefId=4326&where=1%3D1"
FOOTPRINT_DEST="$GEOJSON_DIR/la_county_building_outlines_4326.geojson"

if [[ -f "$FOOTPRINT_DEST" ]]; then
    echo "  already exists: la_county_building_outlines_4326.geojson"
else
    echo "  downloading LA County Building Outlines (large — county-wide, ~2.4M features)..."
    echo "  this may take several minutes."
    wget -q --show-progress -O "$FOOTPRINT_DEST" "$FOOTPRINT_URL" || {
        echo ""
        echo "  WARN: automatic download failed. Download manually:"
        echo "    https://geohub.lacity.org/datasets/lacounty::la-county-building-outlines"
        echo "    Save to: $FOOTPRINT_DEST"
    }
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
