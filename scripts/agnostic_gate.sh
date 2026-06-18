#!/usr/bin/env bash
# Hard-fail the build if a city name is hardcoded in SOURCE.
# configs/, schemas/, fixtures/, tests/, docs/ are allowed to name cities.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
CITIES='miami|new_orleans|nola|los_angeles|new_york|nyc|detroit|south_beach|sobe|miami_dade|baltimore'
HITS=$(grep -rEniI "$CITIES" \
  --include='*.py' --include='*.ts' --include='*.tsx' --include='*.js' \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=configs \
  --exclude-dir=schemas --exclude-dir=fixtures --exclude-dir=tests \
  --exclude-dir=docs . || true)
if [ -n "$HITS" ]; then
  echo "AGNOSTIC GATE FAILED — city name hardcoded in source:"
  echo "$HITS"
  echo "Move the city-specific value into a config under configs/ and read it at runtime."
  exit 1
fi
echo "AGNOSTIC GATE PASSED — no hardcoded cities in source."
