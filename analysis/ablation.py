"""Architectural ablation: identical controller, seven architecture configurations, paired by cell."""
from collections import defaultdict

import numpy as np

import hrc_logs as H
from stats import bca_ci


def analyse(root, allow_non_rt=False):
    runs = H.runs(root, "ablation")
    if not runs:
        return None
    by = defaultdict(lambda: {"exec": [], "jit": [], "medians": [], "miss": 0, "n": 0, "runs": []})
    notes = []
    for d in runs:
        cfg = H.config(d)
        name = cfg["ablation"]["configuration"]
        m = H.manifest(d)
        expected_rt = cfg["rt"]["policy"] == "fifo"
        if expected_rt and not m.get("rt_applied", {}).get("policy_ok", False) and not allow_non_rt:
            notes.append(f"{d.name}: SCHED_FIFO requested but not applied; excluded")
            continue
        c = H.cycles(d)
        e = H.exec_ms(c)
        e = e[np.isfinite(e)]  # 3.1: the last record of a run has no recorded enqueue
        g = by[name]
        g["exec"].append(e.astype(np.float32))
        ri = H.release_interval_ms(c)
        g["jit"].append(ri[~H.flag(c, "release_late")[1:]])
        g["medians"].append(float(np.median(e)))
        g["miss"] += int(H.deadline_miss(c, H.period_ns(d)).sum())
        g["n"] += len(c)
        g["runs"].append(d.name)
    table = {}
    for name in ["A0", "A1", "A2a", "A2b", "A2c", "A2", "A3"]:
        if name not in by:
            continue
        g = by[name]
        E = np.concatenate(g["exec"])
        J = np.concatenate(g["jit"])
        med, ci = bca_ci(np.array(g["medians"]), stat=np.median) if len(g["medians"]) > 2 else (float(np.median(E)), [None, None])
        table[name] = {"runs": len(g["runs"]), "cycles": g["n"], "median_ms": float(np.median(E)),
                       "median_ci95_over_run_medians": ci, "p95_ms": float(np.percentile(E, 95)),
                       "p99_ms": float(np.percentile(E, 99)), "max_ms": float(E.max()), "sd_exec_ms": float(E.std(ddof=1)),
                       "sd_release_interval_ms": float(J.std(ddof=1)), "miss_pct": 100.0 * g["miss"] / g["n"]}
    return {"configurations": table, "notes": notes}
