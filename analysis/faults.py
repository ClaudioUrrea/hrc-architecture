"""Fault detection, recovery, availability and reliability, from raw events and cycles.

Release 3.1 (Reviewer 2, round 4). Definitions, fixed before the 3.1 campaigns:

Matching (one-to-one). Injections are processed in time order. Each is matched to the FIRST
detection of the same category within `window_s` after it that has not already been matched to
an earlier injection; a detection is never credited to two injections. Every injection also
reports, explicitly: other injections within +-window_s (overlapping), whether a condition of
the same category was already active when it arrived (absorbed into an ongoing episode), and
how many candidate detections it had.

Episode. A supervisor condition from its activation (fault_detected) to its clearing
(fault_cleared with the same category and tag; for latched conditions, the operator
acknowledgement). Several injections falling inside one episode are reported as one episode
with several injections; the 1-s re-detection merge rule of release 3.0 is not used.

Recovery (episode-specific). From the matched detection to the clearing of THAT condition, not
to the next return to NOMINAL, which can belong to another active fault (3.0). An injection
whose detection activates no condition (configuration inconsistency: the update is rejected,
the mode is unchanged) has recovery 0 and is marked non-interrupting. Also reported per
injection: stopped time between detection and clearing (cycles with a stop command), which can
overlap with other conditions and is labelled as such.

Availability (three metrics, all time-weighted with timestamps; each record covers
[t_release_i, t_release_{i+1}), so skipped releases are included; the unrecorded start-up and
shut-down intervals are reported):
  outside_stop_modes   time with supervisor mode outside 5-7 (the 3.0 definition)
  motion_permitted     time without a stop command of any origin (supervisor, QP infeasible,
                       limit conflict, final check, mission abort)
  mean_speed_scale     time-weighted envelope fraction; a PROXY for throughput, not a measurement
                       of achieved throughput (task cycles completed are reported separately)

Reliability. Each run starts cold, so its first interval is complete; the last interval of each
run is right-censored. Rates: exact Poisson interval (assumes independent events) AND a
run-level bootstrap interval with the per-run dispersion index (allows clustering). Weibull:
censored MLE reported descriptively, with a parametric-bootstrap goodness of fit that
reproduces the observation process; the plain KS p-value on complete intervals of 3.0 is not
used.

Classification (unchanged):
  service-affecting      every detected fault except configuration inconsistency
  operator-intervention  network partition, constraint violation, memory allocation
"""
from collections import defaultdict

import numpy as np

import hrc_logs as H
from stats import (dispersion_index, poisson_rate_ci, run_bootstrap_rate, weibull_ks, weibull_mle,
                   weibull_param_bootstrap)

OPERATOR = {"network_partition", "constraint_violation", "memory_allocation"}
NON_INTERRUPTING = {"configuration_inconsistency"}
STOP_MODES = {5, 6, 7}


def _clear_for(det, clears):
    """First clearing event of the condition raised by `det` (same category and tag)."""
    for x in clears:
        if x["t_ns"] > det["t_ns"] and x["category"] == det["category"] and x.get("text", "") == det.get("text", ""):
            return x
    return None


def _time_weights(c, period_ns):
    tr = c["t_release_ns"].astype(np.int64)
    w = np.empty(len(c), np.float64)
    if len(c) > 1:
        w[:-1] = np.diff(tr) * 1e-9
    if len(c):
        w[-1] = period_ns * 1e-9
    return w


def _stopped_seconds(c, w, t0_ns, t1_ns):
    m = (c["t_release_ns"] >= t0_ns) & (c["t_release_ns"] < t1_ns) & H.flag(c, "stop_commanded")
    return float(w[m].sum())


def _per_run(d, window_s):
    ev = sorted(H.events(d), key=lambda e: e["t_ns"])
    m = H.manifest(d)
    t0 = m["start_mono_ns"]
    dur = m["duration_s"]
    inj = [e for e in ev if e["kind"] == "fault_injected" and e["text"] == "applied"]
    det = [e for e in ev if e["kind"] == "fault_detected" and e["category"] != "none"]
    clr = [e for e in ev if e["kind"] == "fault_cleared"]
    modes = [e for e in ev if e["kind"] == "mode_change"]
    c = H.cycles(d)
    per = H.period_ns(d)
    w = _time_weights(c, per)
    W = window_s * 1e9  # ns
    reserved = set()
    rows = []
    for i, e in enumerate(inj):
        cat, t = e["category"], e["t_ns"]
        prior = [x for x in modes if x["t_ns"] <= t]
        mode_at = prior[-1]["b"] if prior else 0
        # was a condition of this category already active when the injection arrived?
        active = any(x["category"] == cat and x["t_ns"] <= t and ((cl := _clear_for(x, clr)) is None or cl["t_ns"] > t)
                     for x in det)
        cands = [j for j, x in enumerate(det) if x["category"] == cat and t <= x["t_ns"] <= t + W]
        free = [j for j in cands if j not in reserved]
        overlapping = sum(1 for k, o in enumerate(inj) if k != i and abs(o["t_ns"] - t) <= W)
        same_cat_overlap = sum(1 for k, o in enumerate(inj) if k != i and o["category"] == cat and abs(o["t_ns"] - t) <= W)
        j = free[0] if free else None
        row = {"category": cat, "t_s": (t - t0) * 1e-9, "detected": j is not None, "param": e["detail"],
               "mode_at_injection": mode_at, "condition_already_active": active,
               "candidates_in_window": len(cands), "candidates_reserved_by_earlier": len(cands) - len(free),
               "overlapping_injections": overlapping, "overlapping_same_category": same_cat_overlap,
               "detection_ms": None, "recovery_s": None, "recovery_censored": False, "interrupting": None,
               "stopped_s_until_clear": None}
        if j is not None:
            reserved.add(j)
            d1 = det[j]
            row["detection_ms"] = (d1["t_ns"] - t) * 1e-6
            row["detection_tag"] = d1.get("text", "")
            if cat in NON_INTERRUPTING:
                row["interrupting"] = False
                row["recovery_s"] = 0.0
                row["stopped_s_until_clear"] = 0.0
            else:
                row["interrupting"] = True
                cl = _clear_for(d1, clr)
                t_clear = cl["t_ns"] if cl else t0 + int(dur * 1e9)
                row["recovery_censored"] = cl is None
                row["recovery_s"] = (t_clear - d1["t_ns"]) * 1e-9 if cl else None
                row["stopped_s_until_clear"] = _stopped_seconds(c, w, d1["t_ns"], t_clear)
        rows.append(row)
    # episodes: activation -> clearing of one supervisor condition
    episodes = []
    for x in det:
        cl = _clear_for(x, clr) if x["category"] not in NON_INTERRUPTING else x
        n_inj = sum(1 for e in inj if e["category"] == x["category"] and x["t_ns"] - W <= e["t_ns"] <= (cl["t_ns"] if cl else x["t_ns"] + W))
        episodes.append({"category": x["category"], "tag": x.get("text", ""), "t_s": (x["t_ns"] - t0) * 1e-9,
                         "duration_s": ((cl["t_ns"] - x["t_ns"]) * 1e-9) if cl else None, "injections": n_inj})
    # availability, time-weighted
    T = float(w.sum())
    outside = ~np.isin(c["mode"], list(STOP_MODES))
    permitted = ~H.flag(c, "stop_commanded")
    ctrl_stop = H.flag(c, "qp_failed")
    for k in ("limit_conflict", "final_check_failed"):
        if k in H.FLAGS:
            ctrl_stop = ctrl_stop | H.flag(c, k)
    avail = {"recorded_s": T, "run_duration_s": dur, "unrecorded_s": max(0.0, dur - T),
             "outside_stop_modes_s": float(w[outside].sum()), "motion_permitted_s": float(w[permitted].sum()),
             "controller_stop_outside_stop_modes_s": float(w[ctrl_stop & outside].sum()),
             "speed_scale_time_weighted": float(np.sum(w * c["speed_scale"])) / T if T > 0 else None,
             "cycles": len(c)}
    return rows, episodes, dur, avail


def analyse(root, experiments=("fault_injection",), window_s=2.0, n_boot_weibull=1000):
    runs = [d for exp in experiments for d in H.runs(root, exp)]
    if not runs:
        return None
    allrows, eps_by_run, av = [], [], []
    for d in runs:
        rows, eps, dur, a = _per_run(d, window_s)
        for r in rows:
            r["run"] = d.name
        allrows += rows
        eps_by_run.append((eps, dur))
        av.append(a)
    per = defaultdict(lambda: {"injected": 0, "detected": 0, "det_ms": [], "rec_s": [], "stop_s": [], "censored": 0,
                               "undetected_while_stopped": 0, "undetected_absorbed": 0, "undetected_other": 0,
                               "ambiguous": 0})
    for r in allrows:
        p = per[r["category"]]
        p["injected"] += 1
        p["detected"] += int(r["detected"])
        if r["overlapping_same_category"] or r["candidates_reserved_by_earlier"]:
            p["ambiguous"] += 1
        if not r["detected"]:
            if r["mode_at_injection"] in STOP_MODES:
                p["undetected_while_stopped"] += 1
            elif r["condition_already_active"]:
                p["undetected_absorbed"] += 1
            else:
                p["undetected_other"] += 1
        if r["detection_ms"] is not None:
            p["det_ms"].append(r["detection_ms"])
        if r["recovery_s"] is not None:
            p["rec_s"].append(r["recovery_s"])
        if r["stopped_s_until_clear"] is not None:
            p["stop_s"].append(r["stopped_s_until_clear"])
        p["censored"] += int(r["recovery_censored"])
    med = lambda v: float(np.median(v)) if v else None
    table = {k: {"injected": p["injected"], "detected": p["detected"],
                 "undetected_while_stopped": p["undetected_while_stopped"],
                 "undetected_absorbed_in_ongoing_episode": p["undetected_absorbed"],
                 "undetected_other": p["undetected_other"], "ambiguous_or_overlapping": p["ambiguous"],
                 "detection_ms_median": med(p["det_ms"]), "detection_ms_max": float(np.max(p["det_ms"])) if p["det_ms"] else None,
                 "recovery_s_median": med(p["rec_s"]), "recovery_s_mean": float(np.mean(p["rec_s"])) if p["rec_s"] else None,
                 "recovery_censored": p["censored"], "stopped_s_until_clear_median": med(p["stop_s"]),
                 "interrupting": k not in NON_INTERRUPTING, "operator_intervention_class": k in OPERATOR}
             for k, p in per.items()}
    det_all = [r["detection_ms"] for r in allrows if r["detection_ms"] is not None]
    # reliability over episodes (service-affecting categories)
    intervals, cens, counts_run, exp_run = [], [], [], []
    counts = defaultdict(int)
    n_op_run = []
    for eps, dur in eps_by_run:
        sa = sorted((e for e in eps if e["category"] not in NON_INTERRUPTING), key=lambda e: e["t_s"])
        for e in sa:
            counts[e["category"]] += 1
        counts_run.append(len(sa))
        n_op_run.append(sum(1 for e in sa if e["category"] in OPERATOR))
        exp_run.append(dur / 3600)
        t_prev = 0.0
        for e in sa:
            intervals.append(e["t_s"] - t_prev); cens.append(False)
            t_prev = e["t_s"]
        intervals.append(dur - t_prev); cens.append(True)
    hours = float(np.sum(exp_run))
    n_sa, n_op = int(np.sum(counts_run)), int(np.sum(n_op_run))
    rel = {"exposure_h": hours, "service_affecting_events": n_sa, "operator_intervention_events": n_op,
           "rate_service_affecting_per_h": n_sa / hours,
           "rate_ci95_poisson_exact": poisson_rate_ci(n_sa, hours),
           "rate_ci95_run_bootstrap": run_bootstrap_rate(counts_run, exp_run)[1] if len(runs) > 1 else None,
           "dispersion_across_runs": dispersion_index(counts_run, exp_run),
           "rate_operator_per_h": n_op / hours, "rate_operator_ci95_poisson_exact": poisson_rate_ci(n_op, hours),
           "rate_operator_ci95_run_bootstrap": run_bootstrap_rate(n_op_run, exp_run)[1] if len(runs) > 1 else None,
           "per_category": {k: {"events": v, "rate_per_h": v / hours} for k, v in counts.items()},
           "intervals": {"complete": int(np.sum(~np.array(cens))), "censored": int(np.sum(cens)),
                         "first_interval_treatment": "complete (each run starts cold)"},
           "note": "simulation-campaign rates with design fault rates; not field reliability estimates"}
    t = np.array(intervals) / 3600
    cz = np.array(cens)
    comp = np.sort(t[~cz])
    if comp.size:
        rel["complete_intervals_h_quantiles"] = {q: float(np.quantile(comp, q / 100)) for q in (10, 25, 50, 75, 90)}
    if (~cz).sum() >= 10:
        k, lam = weibull_mle(t, cz)
        ks = weibull_ks(t[~cz], k, lam).statistic
        gof = weibull_param_bootstrap(exp_run, k, lam, ks, n_boot=n_boot_weibull)
        rel["weibull_descriptive"] = {"shape": k, "scale_h": lam, "ks_statistic_complete": float(ks),
                                      "gof_parametric_bootstrap": gof}
    T = sum(a["recorded_s"] for a in av)
    availability = {
        "recorded_s": T, "unrecorded_s": sum(a["unrecorded_s"] for a in av),
        "outside_stop_modes": sum(a["outside_stop_modes_s"] for a in av) / T,
        "motion_permitted": sum(a["motion_permitted_s"] for a in av) / T,
        "difference_controller_stops": sum(a["controller_stop_outside_stop_modes_s"] for a in av) / T,
        "mean_speed_scale_proxy": sum(a["speed_scale_time_weighted"] * a["recorded_s"] for a in av) / T,
        "note": "time-weighted from release timestamps; mean speed scale is a throughput proxy, not a measurement",
    }
    return {"runs": len(runs), "matching_window_s": window_s, "per_category": table, "rows": allrows,
            "detection_ms_all": {"median": med(det_all), "p95": float(np.percentile(det_all, 95)) if det_all else None,
                                 "max": float(np.max(det_all)) if det_all else None},
            "availability": availability, "reliability": rel}
