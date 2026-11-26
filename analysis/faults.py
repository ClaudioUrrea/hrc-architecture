"""Fault detection, recovery, availability and reliability, from raw events and cycles.

Matching: an injection is matched to the first detection of the corresponding category within
`window_s` after it. Recovery: from that detection to the next return to NOMINAL mode. Undetected injections are
split into those that arrived while the cell was already stopped and all others (the latter
include, by design, communication faults shorter than the retry budget and lunges that the
controller stopped before the floor was crossed); the per-injection rows are in `rows`.
Availability is measured directly from the 50 Hz cycle log (fraction of cycles in a stopped
mode), so it contains every downtime source, including simulated operator response times.

Classification used everywhere (one definition):
  service-affecting      every detected fault except configuration inconsistency
  operator-intervention  every fault that latches PROTECTIVE_STOP_LATCHED or EMERGENCY_STOP and
                         therefore needs an acknowledgement: network partition, constraint
                         violation, memory allocation
Reliability: each run starts cold, so its first interval (start -> first event) is a complete
interval; the last interval of each run is right-censored at the run end.
"""
from collections import defaultdict

import numpy as np

import hrc_logs as H
from stats import poisson_rate_ci, weibull_ks, weibull_mle

OPERATOR = {"network_partition", "constraint_violation", "memory_allocation"}
STOP_MODES = {5, 6, 7}


def _per_run(d, window_s):
    ev = sorted(H.events(d), key=lambda e: e["t_ns"])
    m = H.manifest(d)
    t0 = m["start_mono_ns"]
    dur = m["duration_s"]
    inj = [e for e in ev if e["kind"] == "fault_injected" and e["text"] == "applied"]
    det = [e for e in ev if e["kind"] == "fault_detected"]
    modes = [e for e in ev if e["kind"] == "mode_change"]
    rows = []
    for e in inj:
        cat = e["category"]
        t = e["t_ns"]
        prior = [x for x in modes if x["t_ns"] <= t]
        mode_at = prior[-1]["b"] if prior else 0
        d1 = next((x for x in det if x["category"] == cat and t <= x["t_ns"] <= t + window_s * 1e9), None)
        rec = None
        if d1:
            back = next((x for x in modes if x["t_ns"] > d1["t_ns"] and x["b"] == 0), None)
            rec = (back["t_ns"] - d1["t_ns"]) * 1e-9 if back else None
        rows.append({"category": cat, "t_s": (t - t0) * 1e-9, "detected": d1 is not None,
                     "detection_ms": (d1["t_ns"] - t) * 1e-6 if d1 else None, "recovery_s": rec,
                     "mode_at_injection": mode_at, "param": e["detail"]})
    # distinct detected faults (first detection per category episode), for reliability
    episodes = []
    last = {}
    for x in det:
        if x["category"] == "none":  # degradations of the learned component, not faults
            continue
        key = (x["category"], x["text"])
        if key in last and x["t_ns"] - last[key] < 1e9:  # same episode re-detected within 1 s
            continue
        last[key] = x["t_ns"]
        episodes.append({"category": x["category"], "tag": x["text"], "t_s": (x["t_ns"] - t0) * 1e-9})
    c = H.cycles(d)
    stopped = np.isin(c["mode"], list(STOP_MODES))
    return rows, episodes, dur, float(stopped.mean()), float(np.mean(c["speed_scale"])), len(c)


def analyse(root, experiments=("fault_injection",), window_s=2.0):
    runs = [d for exp in experiments for d in H.runs(root, exp)]
    if not runs:
        return None
    allrows, eps_by_run, exposure_s = [], [], 0.0
    stopped_w, scale_w, ncyc = 0.0, 0.0, 0
    for d in runs:
        rows, eps, dur, stop_frac, mean_scale, n = _per_run(d, window_s)
        allrows += rows
        eps_by_run.append((eps, dur))
        exposure_s += dur
        stopped_w += stop_frac * n
        scale_w += mean_scale * n
        ncyc += n
    per = defaultdict(lambda: {"injected": 0, "detected": 0, "det_ms": [], "rec_s": [], "undetected_while_stopped": 0,
                               "undetected_other": 0})
    for r in allrows:
        p = per[r["category"]]
        p["injected"] += 1
        p["detected"] += int(r["detected"])
        if not r["detected"]:
            # an injection that lands while the cell is already stopped cannot change the mode
            if r["mode_at_injection"] in STOP_MODES:
                p["undetected_while_stopped"] += 1
            else:
                p["undetected_other"] += 1
        if r["detection_ms"] is not None:
            p["det_ms"].append(r["detection_ms"])
        if r["recovery_s"] is not None:
            p["rec_s"].append(r["recovery_s"])
    table = {}
    for k, p in per.items():
        table[k] = {"injected": p["injected"], "detected": p["detected"],
                    "undetected_while_stopped": p["undetected_while_stopped"], "undetected_other": p["undetected_other"],
                    "detection_ms_median": float(np.median(p["det_ms"])) if p["det_ms"] else None,
                    "detection_ms_max": float(np.max(p["det_ms"])) if p["det_ms"] else None,
                    "recovery_s_median": float(np.median(p["rec_s"])) if p["rec_s"] else None,
                    "recovery_s_mean": float(np.mean(p["rec_s"])) if p["rec_s"] else None,
                    "operator_intervention_class": k in OPERATOR}
    det_all = [r["detection_ms"] for r in allrows if r["detection_ms"] is not None]
    # reliability over detected episodes
    intervals, cens = [], []
    counts = defaultdict(int)
    for eps, dur in eps_by_run:
        sa = [e for e in eps if e["category"] != "configuration_inconsistency"]
        for e in sa:
            counts[e["category"]] += 1
        t_prev = 0.0
        for e in sa:
            intervals.append(e["t_s"] - t_prev); cens.append(False)
            t_prev = e["t_s"]
        intervals.append(dur - t_prev); cens.append(True)
    hours = exposure_s / 3600
    n_sa = sum(counts.values())
    n_op = sum(v for k, v in counts.items() if k in OPERATOR)
    rel = {"exposure_h": hours, "service_affecting_events": n_sa, "operator_intervention_events": n_op,
           "rate_service_affecting_per_h": n_sa / hours, "rate_ci95": poisson_rate_ci(n_sa, hours),
           "rate_operator_per_h": n_op / hours, "rate_operator_ci95": poisson_rate_ci(n_op, hours),
           "per_category": {k: {"events": v, "rate_per_h": v / hours, "ci95": poisson_rate_ci(v, hours)} for k, v in counts.items()},
           "intervals": {"complete": int(np.sum(~np.array(cens))), "censored": int(np.sum(cens)),
                         "first_interval_treatment": "complete (each run starts cold)"}}
    t = np.array(intervals) / 3600
    cz = np.array(cens)
    if (~cz).sum() >= 10:
        k, lam = weibull_mle(t, cz)
        ks = weibull_ks(t[~cz], k, lam)
        rel["weibull"] = {"shape": k, "scale_h": lam, "ks_p_complete_only": float(ks.pvalue)}
    return {"runs": len(runs), "matching_window_s": window_s, "per_category": table, "rows": allrows,
            "detection_ms_all": {"median": float(np.median(det_all)) if det_all else None,
                                 "p95": float(np.percentile(det_all, 95)) if det_all else None,
                                 "max": float(np.max(det_all)) if det_all else None},
            "availability": {"cycles": ncyc, "unavailable_fraction": stopped_w / ncyc,
                             "availability": 1 - stopped_w / ncyc, "throughput_weighted": scale_w / ncyc,
                             "note": "measured from the cycle log; includes simulated operator response times"},
            "reliability": rel}
