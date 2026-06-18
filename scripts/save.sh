#!/usr/bin/env bash
# End-of-session ritual. You are not done until this prints PUSHED.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
echo "== Repo: $(basename "$(pwd)") =="
git status -sb
if [ -x scripts/agnostic_gate.sh ]; then ./scripts/agnostic_gate.sh; fi
git add -A
git commit -m "${1:-checkpoint: $(date -u +%Y-%m-%dT%H:%MZ)}" || echo "(nothing to commit)"
git push origin HEAD
echo "== PUSHED. origin/$(git branch --show-current) is now safe. =="
