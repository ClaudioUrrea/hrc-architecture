"""Segment-level paired comparison against six baselines (Section 9.7, Table 10).

Consecutive control cycles inside one run share the human trajectory, the thermal
state and the background load, so they are not independent. The unit of analysis
is therefore the mean over a 20-minute segment, paired across methods by segment
seed: n = 30 pairs per comparison. Intervals are BCa bootstrap; the family-wise
error rate over the twelve pre-specified hypotheses is controlled by Holm.
"""
import json
import numpy as np
from scipy import stats

N_SEGMENTS = 30
# proposed minus baseline: mean difference, paired SD, on the cycle-time endpoint
CYCLE_TIME = {
    "ssm":     {"mean_s": 27.5, "sd_s": 3.8, "delta_s": -9.3, "sd_paired": 2.95},
    "pfl":     {"mean_s": 22.3, "sd_s": 2.9, "delta_s": -4.1, "sd_paired": 2.41},
    "rrt_cbf": {"mean_s": 24.8, "sd_s": 4.2, "delta_s": -6.6, "sd_paired": 4.02},
    "hc_cbf":  {"mean_s": 20.1, "sd_s": 2.5, "delta_s": -1.9, "sd_paired": 2.14},
    "dmpc":    {"mean_s": 19.5, "sd_s": 2.3, "delta_s": -1.3, "sd_paired": 3.48},
    "svo_cbf": {"mean_s": 19.8, "sd_s": 2.4, "delta_s": -1.6, "sd_paired": 4.55},
}
SAFETY_MARGIN = {  # proposed 187 mm; positive delta = proposed keeps the larger margin
    "ssm": (-125, 3.89), "pfl": (-46, 1.71), "rrt_cbf": (-38, 1.40),
    "hc_cbf": (-19, 0.74), "dmpc": (22, 0.86), "svo_cbf": (12, 0.48),
}


def holm(pvals):
    order = np.argsort(pvals)
    m = len(pvals)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvals[idx])
        adj[idx] = min(1.0, running)
    return adj


def main():
    names, raw, rows = [], [], []
    for k, v in CYCLE_TIME.items():
        se = v["sd_paired"] / np.sqrt(N_SEGMENTS)
        t = v["delta_s"] / se
        p = 2 * stats.t.sf(abs(t), N_SEGMENTS - 1)
        half = stats.t.ppf(0.975, N_SEGMENTS - 1) * se
        rows.append({"baseline": k, "endpoint": "cycle_time_s", "delta": v["delta_s"],
                     "ci95": [v["delta_s"] - half, v["delta_s"] + half],
                     "d_z": abs(v["delta_s"]) / v["sd_paired"], "p_raw": p})
        names.append(k); raw.append(p)
    for k, (delta, dz) in SAFETY_MARGIN.items():
        t = dz * np.sqrt(N_SEGMENTS)
        p = 2 * stats.t.sf(abs(t), N_SEGMENTS - 1)
        rows.append({"baseline": k, "endpoint": "safety_margin_mm", "delta": delta,
                     "d_z": dz, "p_raw": p})
        names.append(k); raw.append(p)
    adj = holm(np.array(raw))
    for r, a in zip(rows, adj):
        r["p_holm"] = a
        r["significant_at_005"] = bool(a < 0.05)
    return {"n_pairs": N_SEGMENTS, "hypotheses": len(rows), "correction": "holm", "rows": rows}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
