#!/usr/bin/env bash
# Code metrics for Section 5.2 and Figure 3a,c.
# Requires cloc 1.90 and lizard 1.17.10 on PATH.
set -euo pipefail
SRC="${1:-src}"
cloc --json --exclude-dir=tests,third_party,generated "$SRC" > /tmp/cloc.json
lizard -l cpp --csv "$SRC" > /tmp/lizard.csv
python3 - "$SRC" <<'PY'
import json, sys, csv, statistics
cloc = json.load(open('/tmp/cloc.json'))
rows = list(csv.reader(open('/tmp/lizard.csv')))
ccn = [float(r[1]) for r in rows if r and r[1].replace('.','',1).isdigit()]
print(json.dumps({"cpp_code_lines": cloc.get("C++", {}).get("code"),
                  "cyclomatic_mean": round(statistics.mean(ccn), 2) if ccn else None},
                 indent=2))
PY
