#!/usr/bin/env python3
"""Configurations and commanded joint velocities of the study, as input for tools/stop_check.

    python3 tools/stop_samples.py --runs RUNS --experiment timing_campaign --every 250 > samples.csv
    build/stop_check --decel 3.0 --T_r 0.10 --a_stop 1.2 < samples.csv > stop_check.csv

Every `every`-th cycle with a non-zero command is taken from every complete run of the
experiment (q and qd_cmd of the first six joints). Reads only the run directories.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import hrc_logs as H  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--runs", required=True)
ap.add_argument("--experiment", action="append", required=True)
ap.add_argument("--every", type=int, default=250)
a = ap.parse_args()
for exp in a.experiment:
    for d in H.runs(a.runs, exp):
        c = H.cycles(d)
        mv = np.linalg.norm(c["qd_cmd"][:, :6], axis=1) > 0
        sel = np.flatnonzero(mv)[:: a.every]
        for i in sel:
            print(",".join(f"{v:.6f}" for v in np.concatenate([c["q"][i, :6], c["qd_cmd"][i, :6]])))
