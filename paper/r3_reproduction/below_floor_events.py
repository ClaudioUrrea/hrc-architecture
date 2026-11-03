#!/usr/bin/env python3
"""Supplementary analysis S6 (not pre-registered): where the separation fell below the active floor.

    python3 below_floor_events.py --repo /opt/work/hrc3 --runs /opt/work/hrc3/runs --out below_floor.json

For the timing, comparison and injection campaigns, every cycle whose minimum robot-human
separation lies below the floor of its supervisor mode (cycles without a usable estimate are
excluded, as in S2) is grouped into episodes of consecutive cycles. Each episode is related to
the most recent injected fault of the same run (events.jsonl, kind fault_injected / applied), and
the number of consecutive cycles before the episode in which the commanded speed scale was zero is
recorded.
Runs are read through analysis/hrc_logs.py, which verifies every run's SHA-256 manifest first.
Nothing is selected, filtered or re-weighted.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

FLOOR_BY_MODE = [0.15, 0.225, 0.15, 0.30, 0.15, 0.15, 0.15, 0.15]  # include/hrc/supervisor.hpp


def episodes(H, d):
    c = H.cycles(d)
    cfg = H.config(d)
    m = H.manifest(d)
    t0 = m["start_mono_ns"]
    avail = ~H.flag(c, "estimate_unavailable") & (c["min_sep_m"] > -1)
    mode = c["mode"].astype(np.int64)
    floor = np.asarray(FLOOR_BY_MODE)[mode]
    below = avail & (c["min_sep_m"].astype(np.float64) < floor)
    idx = np.flatnonzero(below)
    if len(idx) == 0:
        return []
    inj = sorted((e for e in H.events(d) if e["kind"] == "fault_injected" and e["text"] == "applied"),
                 key=lambda e: e["t_ns"])
    groups, start = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b != a + 1:
            groups.append((start, a)); start = b
    groups.append((start, idx[-1]))
    out = []
    for s, e in groups:
        t = int(c["t_wake_ns"][s])
        prev = [x for x in inj if x["t_ns"] <= t]
        last = prev[-1] if prev else None
        lunge = [x for x in prev if x["category"] == "constraint_violation"]
        seg = c["min_sep_m"][s:e + 1].astype(np.float64)
        k, zeros = s - 1, 0
        while k >= 0 and c["speed_scale"][k] == 0:
            zeros += 1; k -= 1
        out.append({
            "run": d.name, "strategy": cfg["control"]["strategy"],
            "t_s": round((t - t0) * 1e-9, 3), "cycles": int(e - s + 1),
            "min_sep_m": round(float(seg.min()), 4),
            "floor_m": float(floor[s]), "mode_first": int(mode[s]),
            "modes": sorted(set(int(x) for x in mode[s:e + 1])),
            "last_injection": None if last is None else {"category": last["category"],
                                                          "dt_s": round((t - last["t_ns"]) * 1e-9, 3)},
            "last_lunge_dt_s": None if not lunge else round((t - lunge[-1]["t_ns"]) * 1e-9, 3),
            "zero_speed_cycles_before": int(zeros),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.repo) / "analysis"))
    import hrc_logs as H
    res = {"note": "supplementary analysis S6 (not pre-registered); same runs, same readers, no run selected or excluded",
           "floor_by_mode": FLOOR_BY_MODE}
    for exp in ("timing_campaign", "baseline_compare", "fault_injection"):
        eps = []
        n = 0
        for d in H.runs(a.runs, exp):
            n += 1
            eps += episodes(H, d)
        within3 = [x for x in eps if x["last_lunge_dt_s"] is not None and x["last_lunge_dt_s"] <= 3.0]
        zl = [x["zero_speed_cycles_before"] for x in within3]
        res[exp] = {"runs": n, "episodes": len(eps), "cycles": sum(x["cycles"] for x in eps),
                    "episodes_within_3s_of_lunge": len(within3),
                    "cycles_within_3s_of_lunge": sum(x["cycles"] for x in within3),
                    "lunge_episodes_with_negative_separation": sum(1 for x in within3 if x["min_sep_m"] < 0),
                    "lunge_episodes_speed_already_zero": sum(1 for z in zl if z > 0),
                    "lunge_zero_speed_cycles_before_min": min(zl) if zl else None,
                    "lunge_zero_speed_cycles_before_median": float(np.median(zl)) if zl else None,
                    "list": eps}
        print(f"{exp}: {n} runs, {len(eps)} episodes, {res[exp]['cycles']} cycles, "
              f"{len(within3)} episodes within 3 s of a lunge", flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
