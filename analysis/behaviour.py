"""Release 3.1: safety behaviour from the per-cycle fields added in 3.1 (Reviewer 2, round 4).

Per experiment and strategy:
  * dispatched command: largest logged violation of every barrier row, the reduced box and the
    SSM limit (final_viol; must be <= 1e-6), and controller-level stops by cause;
  * estimate vs simulator ground truth: error of the estimate's keypoint closest to the robot
    and of its worst keypoint (against ssm.Z_d and control.position_margin of the run), and the
    difference between the estimated and the true separation;
  * floor crossings, separately on the ESTIMATED separation and on the TRUE separation. The
    floor of each cycle is the supervisor floor composed over the active conditions (cond_mask).
    A crossing episode is a maximal run of consecutive cycles below the floor. For its first
    cycle the robot state is classified from the logged command and measured joint speed:
      standstill        |qd_measured| < 1e-3 rad/s
      decelerating      not standstill, and a stop or a zero command was issued in this or the
                        previous cycle
      moving            not standstill, non-zero command (the controller was still moving it)
    together with the supervisor mode, whether an injected lunge started in the preceding 2 s,
    and the minimum separation (true and estimated) within the episode.
Quantiles come from 1-mm histograms (exact to 1 mm) so that 3.6e7 cycles fit in memory.
"""
from collections import defaultdict

import numpy as np

import hrc_logs as H

FLOORS = np.array([0.15, 0.225, 0.15, 0.30, 0.15, 0.15, 0.15, 0.15])  # SupervisorParams.floor_m
STANDSTILL = 1e-3
EDGES_ERR = np.arange(0.0, 2.0005, 0.001)
EDGES_DIF = np.arange(-1.0, 1.0005, 0.001)


def _floor(c):
    m = c["cond_mask"].astype(np.int64)
    f = np.full(len(c), FLOORS[0])
    for k in range(1, 8):
        f = np.where((m >> k) & 1, np.maximum(f, FLOORS[k]), f)
    return f


def _q(hist, edges, qs=(50, 95, 99)):
    n = hist.sum()
    if n == 0:
        return None
    cdf = np.cumsum(hist) / n
    out = {f"p{q}": float(edges[min(len(edges) - 1, np.searchsorted(cdf, q / 100) + 1)]) for q in qs}
    out["n"] = int(n)
    return out


def _episodes(below):
    idx = np.flatnonzero(below)
    if idx.size == 0:
        return []
    cuts = np.flatnonzero(np.diff(idx) > 1)
    starts = np.r_[idx[0], idx[cuts + 1]]
    ends = np.r_[idx[cuts], idx[-1]]
    return list(zip(starts, ends))


def _classify(c, i):
    still = c["qd_meas_norm"][i] < STANDSTILL
    zero_now = H.flag(c, "stop_commanded")[i] or not np.any(c["qd_cmd"][i])
    zero_prev = i > 0 and (H.flag(c, "stop_commanded")[i - 1] or not np.any(c["qd_cmd"][i - 1]))
    if still:
        return "standstill"
    if zero_now or zero_prev:
        return "decelerating"
    return "moving"


def analyse(root, experiment):
    runs = H.runs(root, experiment)
    runs = [d for d in runs if "gt_min_sep_m" in H.cycle_dtype(d).names]
    if not runs:
        return None
    G = defaultdict(lambda: {"runs": 0, "cycles": 0, "dispatched": 0, "final_viol_max": 0.0, "final_check_failed": 0,
                             "qp_failed": 0, "limit_conflict": 0, "ssm_reduced": 0,
                             "h_close": np.zeros(len(EDGES_ERR) - 1, np.int64), "h_max": np.zeros(len(EDGES_ERR) - 1, np.int64),
                             "h_dif": np.zeros(len(EDGES_DIF) - 1, np.int64), "above_margin": 0, "above_zd": 0, "matched": 0,
                             "est": [], "gt": [], "gt_below_while_est_above": 0, "Z_d": set(), "margin": set()})
    for d in runs:
        cfg = H.config(d)
        g = G[cfg.get("control", {}).get("strategy", "proposed")]
        c = H.cycles(d)
        ev = H.events(d)
        lunges = np.array([e["t_ns"] for e in ev if e["kind"] == "fault_injected" and e["text"] == "applied"
                           and e["category"] == "constraint_violation"], dtype=np.int64)
        zd = cfg.get("ssm", {}).get("Z_d", 0.04)
        mg = cfg.get("control", {}).get("position_margin", 0.0)
        g["Z_d"].add(zd); g["margin"].add(mg)
        stop = H.flag(c, "stop_commanded")
        g["runs"] += 1
        g["cycles"] += len(c)
        g["dispatched"] += int((~stop).sum())
        if (~stop).any():
            g["final_viol_max"] = max(g["final_viol_max"], float(c["final_viol"][~stop].max()))
        for k in ("final_check_failed", "qp_failed", "limit_conflict", "ssm_reduced"):
            g[k] += int(H.flag(c, k).sum())
        em = c["est_err_max_m"]
        ec = c["est_err_closest_m"] if "est_err_closest_m" in c.dtype.names else np.full(len(c), np.nan, np.float32)
        f = np.isfinite(ec)
        g["matched"] += int(f.sum())
        g["above_zd"] += int((ec[f] > zd).sum())
        g["above_margin"] += int((ec[f] > mg).sum())
        g["h_close"] += np.histogram(ec[f], EDGES_ERR)[0]
        g["h_max"] += np.histogram(em[np.isfinite(em)], EDGES_ERR)[0]
        gt, est = c["gt_min_sep_m"], c["min_sep_m"]
        ok = np.isfinite(gt) & (est > -1)
        g["h_dif"] += np.histogram(est[ok] - gt[ok], EDGES_DIF)[0]
        fl = _floor(c)
        below_est = (est > -1) & (est < fl)
        below_gt = np.isfinite(gt) & (gt < fl)
        g["gt_below_while_est_above"] += int((below_gt & ~below_est & (est > -1)).sum())
        t = c["t_wake_ns"]
        for key, below in (("est", below_est), ("gt", below_gt)):
            for s, e in _episodes(below):
                lead = lunges[(lunges <= t[s]) & (lunges >= t[s] - 2_000_000_000)]
                g[key].append({"run": d.name, "cycle": int(c["idx"][s]), "cycles": int(e - s + 1),
                               "state_at_onset": _classify(c, s), "mode": int(c["mode"][s]), "floor_m": float(fl[s]),
                               "lunge_within_2s": bool(lead.size),
                               "min_true_sep_m": float(np.nanmin(gt[s:e + 1])) if np.isfinite(gt[s:e + 1]).any() else None,
                               "min_est_sep_m": float(est[s:e + 1][est[s:e + 1] > -1].min()) if (est[s:e + 1] > -1).any() else None})
    out = {}
    for strat, g in G.items():
        def summ(eps):
            by_state = defaultdict(int)
            for x in eps:
                by_state[x["state_at_onset"]] += 1
            return {"episodes": len(eps), "cycles": int(sum(x["cycles"] for x in eps)), "state_at_onset": dict(by_state),
                    "with_lunge_within_2s": sum(x["lunge_within_2s"] for x in eps),
                    "in_nominal_mode": sum(x["mode"] == 0 for x in eps),
                    "min_true_sep_m": min((x["min_true_sep_m"] for x in eps if x["min_true_sep_m"] is not None), default=None),
                    "list": eps}
        out[strat] = {"runs": g["runs"], "cycles": g["cycles"], "dispatched_cycles": g["dispatched"],
                      "final_viol_max": g["final_viol_max"], "final_check_failed": g["final_check_failed"],
                      "controller_stops": {"qp_failed": g["qp_failed"], "limit_conflict": g["limit_conflict"]},
                      "ssm_reduced_cycles": g["ssm_reduced"],
                      "Z_d_m": sorted(g["Z_d"]), "position_margin_m": sorted(g["margin"]),
                      "estimate_error_closest_m": _q(g["h_close"], EDGES_ERR),
                      "estimate_error_worst_keypoint_m": _q(g["h_max"], EDGES_ERR),
                      "share_closest_error_above_Z_d": g["above_zd"] / g["matched"] if g["matched"] else None,
                      "share_closest_error_above_margin": g["above_margin"] / g["matched"] if g["matched"] else None,
                      "estimated_minus_true_separation_m": _q(g["h_dif"], EDGES_DIF, (1, 5, 50, 95, 99)),
                      "below_floor_estimated": summ(g["est"]), "below_floor_true": summ(g["gt"]),
                      "true_below_floor_while_estimate_above_cycles": g["gt_below_while_est_above"]}
    return out
