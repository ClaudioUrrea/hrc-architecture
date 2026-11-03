#!/usr/bin/env python3
"""Position-uncertainty calibration of release 3.1 (rule fixed before the calibration runs).

    python3 tools/calibrate_position_margin.py --runs runs --apply

Rule (docs/PREREGISTRATION_3.1.md, published before the calibration runs):
  1. Input: every complete run of experiment "calibration" (cfg/campaigns/calibration: S1-S6,
     10 min each, proposed strategy, no faults, position margin 0).
  2. Statistic: the 99th percentile q99 of est_err_closest_m (error of the estimated keypoint
     closest to the robot against the simulator ground truth at the estimate's observation
     time), pooled over all cycles in which it was matched.
  3. Margin m = q99 rounded UP to the next centimetre.
  4. control.position_margin = m (subtracted from every geometric barrier value) and
     ssm.Z_d = max(0.04, m) (ISO/TS 15066 human position uncertainty) in cfg/base_sim_ur5e.json.
No other parameter is changed. With --apply the base configuration is rewritten and
cfg/calibration_v4.json records the inputs (run directories and manifest hashes), the
statistic and the values applied.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import hrc_logs as H  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--runs", default="runs")
ap.add_argument("--apply", action="store_true")
ap.add_argument("--expected-runs", type=int, default=6)
a = ap.parse_args()

runs = H.runs(a.runs, "calibration")
if len(runs) != a.expected_runs:
    sys.exit(f"calibration: {len(runs)} complete runs, expected {a.expected_runs}; not applying")
errs, per_run = [], []
for d in runs:
    c = H.cycles(d)
    e = c["est_err_closest_m"]
    e = e[np.isfinite(e)]
    errs.append(e)
    per_run.append({"run": d.name, "manifest_sha256": hashlib.sha256((d / "MANIFEST.sha256").read_bytes()).hexdigest(),
                    "cycles": int(len(c)), "matched": int(len(e)),
                    "p50": float(np.percentile(e, 50)), "p99": float(np.percentile(e, 99))})
E = np.concatenate(errs)
q99 = float(np.percentile(E, 99))
m = math.ceil(q99 * 100 - 1e-9) / 100
out = {"rule": "position_margin = ceil_cm(p99(est_err_closest_m)); Z_d = max(0.04, position_margin)",
       "pooled": {"matched_cycles": int(len(E)), "p50": float(np.percentile(E, 50)), "p95": float(np.percentile(E, 95)),
                  "p99": q99, "max": float(E.max())},
       "position_margin_m": m, "Z_d_m": max(0.04, m), "runs": per_run}
print(json.dumps(out, indent=1))
if a.apply:
    b = ROOT / "cfg" / "base_sim_ur5e.json"
    c = json.loads(b.read_text())
    c["control"]["position_margin"] = m
    c["ssm"]["Z_d"] = max(0.04, m)
    b.write_text(json.dumps(c, indent=2) + "\n")
    (ROOT / "cfg" / "calibration_v4.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"applied: control.position_margin={m} ssm.Z_d={max(0.04, m)}")
