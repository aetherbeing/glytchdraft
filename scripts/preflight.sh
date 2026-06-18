#!/usr/bin/env bash
# Phase 00 — Source-of-Truth Preflight. Run before ANY work.
set -euo pipefail
echo "== GlytchOS Preflight =="
echo "machine : $(hostname)"
echo "pwd     : $(pwd)"
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "FAIL: not in a git repo. STOP."; exit 1; }
echo "repo    : $ROOT"
echo "remote  :"; git remote -v | sed 's/^/          /'
echo "branch  : $(git branch --show-current)"
echo "status  :"; git status -sb | sed 's/^/          /'
echo "== Confirm intended repo, branch, machine before proceeding. =="
