#!/usr/bin/env bash
# Line counts (cloc) and cyclomatic complexity (lizard) of the C++ sources, written as a run
# directory with a SHA-256 manifest. Requires: cloc, lizard (pip install lizard), git.
set -euo pipefail
cd "$(dirname "$0")/.."
ts=$(date -u +%Y-%m-%dT%H-%M-%S)Z
out=${1:-runs}/${ts}_code_metrics
mkdir -p "$out"
git rev-parse HEAD > "$out/commit.txt" 2>/dev/null || echo "no-git" > "$out/commit.txt"
git status --porcelain > "$out/git_status.txt" 2>/dev/null || true
# shared core vs. per-vendor adapter code; tests and third-party code excluded
cloc --json --quiet include src/common src/log src/kin src/rt src/safety src/control src/integration src/faults src/ipc src/sim > "$out/cloc_shared.json"
for f in src/adapters/ur_rtde.cpp src/adapters/kuka_fri.cpp src/adapters/abb_egm.cpp; do
  cloc --json --quiet "$f" > "$out/cloc_$(basename "$f" .cpp).json"
done
lizard -l cpp --csv include src > "$out/lizard.csv"
cloc --version > "$out/tool_versions.txt"; lizard --version >> "$out/tool_versions.txt"
( cd "$out" && sha256sum * > MANIFEST.sha256 )
echo "$out"
