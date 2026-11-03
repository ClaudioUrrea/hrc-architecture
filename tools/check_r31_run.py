#!/usr/bin/env python3
"""Checks of the release-3.1 code paths on raw run directories (pilot or campaign).

    python3 tools/check_r31_run.py RUN_DIR [RUN_DIR ...]

Per run: cycles; dispatched (non-stop) cycles; largest violation of the dispatched command
(must be <= 1e-6: every barrier row, the reduced box and the SSM limit hold for what was sent);
controller-level stops by cause; SSM-reduced cycles; cycles with several supervisor conditions
active at once; execution time with the enqueue included; ground-truth vs estimated separation;
estimate error vs the assumed human position uncertainty Z_d; floor crossings on the estimate
and on ground truth, each classified by the robot's state (zero command / decelerating /
standstill). Reads only the run directory; writes nothing.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import hrc_logs as H  # noqa: E402

STANDSTILL = 1e-3  # rad/s, |measured joint velocity| below which the robot counts as stopped


def floor_of(c, cfg):
    # active floor per cycle is not logged directly; the supervisor floor is a function of the
    # active conditions: max over active conditions of floor_m[k] (defaults of SupervisorParams)
    floors = np.array([0.15, 0.225, 0.15, 0.30, 0.15, 0.15, 0.15, 0.15])
    m = c["cond_mask"].astype(np.int64)
    f = np.full(len(c), floors[0])
    for k in range(1, 8):
        f = np.where((m >> k) & 1, np.maximum(f, floors[k]), f)
    return f


def classify(c, idx):
    stop = H.flag(c, "stop_commanded")[idx]
    zero_cmd = np.linalg.norm(c["qd_cmd"][idx], axis=1) == 0
    still = c["qd_meas_norm"][idx] < STANDSTILL
    return {"standstill": int(np.sum(still)), "decelerating_after_zero_or_stop": int(np.sum(~still & (zero_cmd | stop))),
            "moving_with_nonzero_command": int(np.sum(~still & ~(zero_cmd | stop)))}


def check(d):
    d = Path(d)
    c = H.cycles(d)
    cfg = H.config(d)
    n = len(c)
    stop = H.flag(c, "stop_commanded")
    disp = ~stop
    out = {"run": d.name, "status": H.manifest(d).get("status"), "cycles": n, "dispatched": int(disp.sum())}
    fv = c["final_viol"][disp]
    out["final_viol_max"] = float(fv.max()) if fv.size else 0.0
    out["final_check_failed"] = int(H.flag(c, "final_check_failed").sum())
    out["stops"] = {k: int(H.flag(c, k).sum()) for k in ("qp_failed", "limit_conflict", "final_check_failed")}
    out["stops"]["supervisor_or_mission"] = int((stop & ~(H.flag(c, "qp_failed") | H.flag(c, "limit_conflict") | H.flag(c, "final_check_failed"))).sum())
    out["ssm_reduced"] = int(H.flag(c, "ssm_reduced").sum())
    multi = np.array([bin(int(x)).count("1") for x in c["cond_mask"]]) >= 2
    out["cycles_with_2plus_conditions"] = int(multi.sum())
    e = H.exec_ms(c)
    e = e[np.isfinite(e)]
    enq = c["d_enqueue_prev_ns"][1:] * 1e-3
    out["exec_ms"] = {"median": float(np.median(e)), "p99": float(np.percentile(e, 99)), "max": float(e.max())}
    out["enqueue_us"] = {"median": float(np.median(enq)), "max": float(enq.max())}
    out["deadline_misses"] = int(H.deadline_miss(c, H.period_ns(d)).sum())
    gt = c["gt_min_sep_m"]
    est = c["min_sep_m"]
    ok = np.isfinite(gt) & (est > -1)
    out["gt_available"] = int(np.isfinite(gt).sum())
    out["gt_age_ms_max"] = float(np.nanmax(c["gt_age_ms"])) if np.isfinite(c["gt_age_ms"]).any() else None
    if ok.any():
        dlt = est[ok] - gt[ok]
        out["est_minus_gt_sep_m"] = {"median": float(np.median(dlt)), "p1": float(np.percentile(dlt, 1)),
                                     "p99": float(np.percentile(dlt, 99))}
    zd = cfg.get("ssm", {}).get("Z_d", 0.04)
    fields = ["est_err_max_m"] + (["est_err_closest_m"] if "est_err_closest_m" in c.dtype.names else [])
    for name in fields:
        err = c[name]
        fe = np.isfinite(err)
        if fe.any():
            out[name] = {"matched_cycles": int(fe.sum()), "median": float(np.median(err[fe])),
                         "p95": float(np.percentile(err[fe], 95)), "p99": float(np.percentile(err[fe], 99)),
                         "max": float(err[fe].max()), "Z_d": zd, "share_above_Z_d": float(np.mean(err[fe] > zd))}
    fl = floor_of(c, cfg)
    below_est = (est > -1) & (est < fl)
    below_gt = np.isfinite(gt) & (gt < fl)
    out["below_floor"] = {"estimate": {"cycles": int(below_est.sum()), **classify(c, below_est)},
                          "ground_truth": {"cycles": int(below_gt.sum()), **classify(c, below_gt)},
                          "gt_min_m": float(np.nanmin(gt)) if np.isfinite(gt).any() else None}
    return out


if __name__ == "__main__":
    res = [check(d) for d in sys.argv[1:]]
    print(json.dumps(res, indent=1))
    bad = [r["run"] for r in res if r["final_viol_max"] > 1e-6]
    sys.exit(1 if bad else 0)
