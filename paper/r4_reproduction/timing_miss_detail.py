#!/usr/bin/env python3
"""Supplementary detail for manuscript R4 (specified after the campaigns; not pre-registered).

    python3 timing_miss_detail.py --repo /opt/work/hrc31 --runs /opt/work/hrc31/runs --out timing_miss_detail.json

(1) For every timing block with a deadline miss among its retained cycles, the wake-up delay
    (t_wake - t_release) and the execution time from wake-up of each missed cycle, read through the
    repository's own reader (analysis/hrc_logs.py, which verifies the run manifest first) and with the
    pre-registered miss definition (hrc_logs.deadline_miss) and overrun mask (flag injected_overrun).
(2) The run directories that were opened but never closed (status "running", no manifest), by
    experiment: these are the runs interrupted by an incident and run again from the start.
Nothing is read from the manuscript; no run is modified.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.repo) / "analysis"))
    import hrc_logs as H

    out = {"note": __doc__.strip().splitlines()[0], "blocks_with_retained_miss": [], "unclosed_runs": {}}
    for d in H.runs(a.runs, experiment="timing_campaign"):
        c = H.cycles(d)
        over = H.deadline_miss(c, H.period_ns(d))
        inj = H.flag(c, "injected_overrun")
        ret = over & ~inj
        if not ret.any():
            continue
        idx = np.nonzero(ret)[0]
        wake = (c["t_wake_ns"][idx].astype(np.int64) - c["t_release_ns"][idx].astype(np.int64)) / 1e6
        exe = H.exec_ms(c)[idx]
        t = (c["t_release_ns"][idx].astype(np.int64) - int(c["t_release_ns"][0])) / 1e9
        out["blocks_with_retained_miss"].append({
            "run": Path(d).name, "misses": int(len(idx)),
            "wake_delay_ms": [round(float(x), 3) for x in wake],
            "exec_from_wake_ms": [round(float(x), 4) for x in exe],
            "t_since_block_start_s": [round(float(x), 2) for x in t],
            "max_estimate_age_ms": float(np.max(c["human_age_ms"])),
        })
    for d in sorted(Path(a.runs).iterdir()):
        if not d.is_dir() or (d / "MANIFEST.sha256").exists():
            continue
        try:
            exp = json.loads((d / "manifest.json").read_text()).get("experiment", "?")
        except Exception:
            exp = "?"
        out["unclosed_runs"].setdefault(exp, []).append(d.name)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: (v if k != "blocks_with_retained_miss" else [(b["run"], b["misses"]) for b in v])
                      for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
