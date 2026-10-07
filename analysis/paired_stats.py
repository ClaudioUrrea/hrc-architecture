"""Segment-level paired comparison against six baselines (Section 9.7, Table 12).

Consecutive control cycles inside one run share the human trajectory, the thermal
state and the background load, so they are not independent. The unit of analysis
is therefore the mean over a 20-minute segment, paired across methods by segment
seed: n = 30 pairs per comparison. The family-wise error rate over the twelve
pre-specified hypotheses (six baselines x two endpoints) is controlled by Holm.

v2.1.0. Every number is recomputed from data/segments_30.parquet; the constants
that used to sit here (and that were the untuned numbers of the first submission)
are gone. The primary comparison uses the TUNED parameter set; the untuned set
is reported alongside for the record.

Two interval types are returned for the paired difference (proposed minus
baseline): the t interval (n - 1 = 29 d.f.) and the BCa bootstrap interval
(10,000 resamples, seed in config/seeds.json). Table 12 of the manuscript prints
the BCa interval, as Section 9.7 states; the t interval is kept for comparison
(in v2.1.0-draft the manuscript printed t intervals under a BCa label, corrected
in the final v2.1.0 revision). For n = 30 they differ by a few percent of the width.
"""
import json
import os
import numpy as np
import pyarrow.parquet as pq
from scipy import stats

from hrc_stats import bca_ci, holm

PATH = "data/segments_30.parquet"
BASELINES = ["SSM", "RRT-CBF", "PFL", "HC-CBF", "SVO-CBF", "DMPC"]
ENDPOINTS = {"cycle": "cycle_time_s", "margin": "min_margin_mm"}


def _seed():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "seeds.json")
    return json.load(open(p))["bootstrap"]["bca_segments"]


def _series(d, method, pset, col):
    g = d[(d.method == method) & (d.parameter_set == pset)].sort_values("segment_id")
    return g[col].to_numpy(float)


def compare(d, pset):
    n = d[(d.method == "Proposed")].segment_id.nunique()
    rows = []
    for ep, col in ENDPOINTS.items():
        prop = _series(d, "Proposed", "proposed", col)
        for b in BASELINES:
            base = _series(d, b, pset, col)
            diff = prop - base
            sd = float(diff.std(ddof=1))
            se = sd / np.sqrt(n)
            t = diff.mean() / se
            p = float(2 * stats.t.sf(abs(t), n - 1))
            half = stats.t.ppf(0.975, n - 1) * se
            lo, hi = bca_ci(diff, seed=_seed())
            rows.append({"baseline": b, "endpoint": ep,
                         "baseline_mean": round(float(base.mean()), 2), "baseline_sd": round(float(base.std(ddof=1)), 2),
                         "delta": round(float(diff.mean()), 3), "sd_paired": round(sd, 3),
                         "ci95_t": [round(diff.mean() - half, 2), round(diff.mean() + half, 2)],
                         "ci95_bca": [round(lo, 2), round(hi, 2)],
                         "d_z": round(abs(float(diff.mean())) / sd, 3), "p_raw": p})
    adj = holm(np.array([r["p_raw"] for r in rows]))
    for r, a in zip(rows, adj):
        r["p_holm"] = float(a)
        r["significant_at_005"] = bool(a < 0.05)
    return rows


def main(path=PATH):
    d = pq.read_table(path).to_pandas()
    n = int(d[d.method == "Proposed"].segment_id.nunique())
    out = {"source": path, "n_pairs": n, "hypotheses": 12, "correction": "holm", "primary": "tuned",
           "proposed": {ep: {"mean": round(float(_series(d, "Proposed", "proposed", c).mean()), 2),
                             "sd": round(float(_series(d, "Proposed", "proposed", c).std(ddof=1)), 2)}
                        for ep, c in ENDPOINTS.items()},
           "tuned": compare(d, "tuned"), "untuned": compare(d, "untuned")}
    pr = d[d.method == "Proposed"]
    cl, cg = pr.conservatism_learned_pct.to_numpy(float), pr.conservatism_geometric_pct.to_numpy(float)
    h = stats.t.ppf(0.975, n - 1) / np.sqrt(n)
    out["conservatism_pct"] = {"learned": {"mean": round(cl.mean(), 1), "ci95": [round(cl.mean() - h * cl.std(ddof=1), 1), round(cl.mean() + h * cl.std(ddof=1), 1)]},
                               "geometric": {"mean": round(cg.mean(), 1), "ci95": [round(cg.mean() - h * cg.std(ddof=1), 1), round(cg.mean() + h * cg.std(ddof=1), 1)]}}
    # lag-1 autocorrelation of every series (segments are meant to be exchangeable)
    ac = []
    for (m, ps), g in d.groupby(["method", "parameter_set"]):
        for c in ENDPOINTS.values():
            x = g.sort_values("segment_id")[c].to_numpy(float)
            ac.append(abs(float(np.corrcoef(x[:-1], x[1:])[0, 1])))
    out["max_abs_lag1_autocorrelation"] = round(max(ac), 3)
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
