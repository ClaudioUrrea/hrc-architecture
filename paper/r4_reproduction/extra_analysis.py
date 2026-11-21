#!/usr/bin/env python3
"""Supplementary analyses for manuscript R4 (release 3.1, campaigns v4); not part of the
pre-registered report (analysis/report.py at tag campaign-v4-report).

    python3 extra_analysis.py --repo /opt/work/hrc31 --runs /opt/work/hrc31/runs \
        --results /opt/work/hrc31/results/results.json --out results_extra.json

Every quantity is computed from raw run directories through the repository's own readers
(analysis/hrc_logs.py), which verify each run's SHA-256 manifest before reading it. Nothing is
read from the manuscript. They are labelled "supplementary" in the paper because they were
specified after the pre-registration (they describe the same runs in more detail; they do not
select, filter or re-weight any run):

  S1  fault_sensitivity broken down by run (arrival model x rate scale), with the pre-registered
      function analysis/faults.analyse applied to one run at a time;
  S2  safety-layer behaviour per campaign: occupancy of each reported mode, cycles with more than
      one active condition, cycles in which the limits composed over the active conditions are
      stricter than those of the reported mode alone, use of the learned rows, flags, share of
      the closest-keypoint estimate error above the release-3.0 value Z_d = 0.04 m;
  S3  per-block timing summaries, duration of the enqueue of the cycle record, and pooled
      histograms (for the figures);
  S4  code metrics (cloc / lizard) of the run directory written by tools/code_metrics.sh;
  S5  injection rows split by injected parameter (communication faults: length of the corrupt
      burst; lunges: whether a floor violation was detected), from the pre-registered matching.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

STOP_MODES = (5, 6, 7)
SCALE_BY_COND = np.array([1.0, 0.7, 0.5, 0.5, 1.0, 0.0, 0.0, 0.0])      # SupervisorParams.speed_scale
FLOOR_BY_COND = np.array([0.15, 0.225, 0.15, 0.30, 0.15, 0.15, 0.15, 0.15])  # SupervisorParams.floor_m
OLD_ZD = 0.04
EXEC_BINS_MS = np.concatenate([np.arange(0, 1, 0.005), np.arange(1, 10, 0.05), np.arange(10, 60.5, 0.5)])
AGE_BINS_MS = np.arange(0, 200.5, 0.5)
SEP_BINS_M = np.arange(-0.2, 3.0001, 0.005)
ERR_BINS_M = np.arange(0.0, 1.0005, 0.002)
ENQ_BINS_US = np.concatenate([np.arange(0, 20, 0.05), np.arange(20, 2000.5, 0.5)])


def load_repo(repo):
    sys.path.insert(0, str(Path(repo) / "analysis"))
    import faults  # noqa: E402
    import hrc_logs as H  # noqa: E402
    return H, faults


def hist(x, bins):
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    h, _ = np.histogram(np.clip(x, bins[0], bins[-1] - 1e-9), bins=bins)
    return h.astype(np.int64)


def composed(mask):
    """Speed scale and floor composed over the active conditions (cond_mask bits 1..7)."""
    m = mask.astype(np.int64)
    s = np.full(len(m), SCALE_BY_COND[0])
    fl = np.full(len(m), FLOOR_BY_COND[0])
    n_active = np.zeros(len(m), np.int64)
    for k in range(1, 8):
        on = ((m >> k) & 1).astype(bool)
        s = np.where(on, np.minimum(s, SCALE_BY_COND[k]), s)
        fl = np.where(on, np.maximum(fl, FLOOR_BY_COND[k]), fl)
        n_active += on
    return s, fl, n_active


# ------------------------------------------------------------------------------------- S1
def _analyse_single(H, faults, run_dir, experiment):
    """faults.analyse restricted to one run directory, without modifying the analysis code."""
    orig = faults.H.runs
    try:
        faults.H.runs = lambda root, exp=None, include_incomplete=False: [run_dir]
        return faults.analyse(str(run_dir.parent), (experiment,))
    finally:
        faults.H.runs = orig


def sensitivity_by_config(H, faults, runs_root):
    out = []
    for d in H.runs(runs_root, "fault_sensitivity"):
        cfg = H.config(d)["faults"]
        res = _analyse_single(H, faults, d, "fault_sensitivity")
        rel, av = res["reliability"], res["availability"]
        out.append({"run": d.name, "variant": H.config(d).get("variant"), "arrival": cfg.get("arrival"),
                    "weibull_shape": cfg.get("weibull_shape"), "mean_cluster_size": cfg.get("mean_cluster_size"),
                    "rate_scale": cfg.get("rate_scale"),
                    "injected": sum(v["injected"] for v in res["per_category"].values()),
                    "detected": sum(v["detected"] for v in res["per_category"].values()),
                    "availability": av["outside_stop_modes"], "motion_permitted": av["motion_permitted"],
                    "mean_speed_scale": av["mean_speed_scale_proxy"],
                    "exposure_h": rel["exposure_h"],
                    "service_affecting_events": rel["service_affecting_events"],
                    "operator_intervention_events": rel["operator_intervention_events"],
                    "rate_service_affecting_per_h": rel["rate_service_affecting_per_h"],
                    "rate_ci95_poisson_exact": rel["rate_ci95_poisson_exact"],
                    "detection_ms_median": res["detection_ms_all"]["median"]})
    return out


# ------------------------------------------------------------------------------------- S2, S3
def campaign_behaviour(H, runs_root, experiment, per_block=False):
    runs = H.runs(runs_root, experiment)
    if not runs:
        return None
    mode_counts = np.zeros(8, dtype=np.int64)
    flags = Counter()
    n = multi = stricter = 0
    err_n = err_old = 0
    h_exec = np.zeros(len(EXEC_BINS_MS) - 1, np.int64)
    h_age = np.zeros(len(AGE_BINS_MS) - 1, np.int64)
    h_sep = np.zeros(len(SEP_BINS_M) - 1, np.int64)
    h_gt = np.zeros(len(SEP_BINS_M) - 1, np.int64)
    h_err = np.zeros(len(ERR_BINS_M) - 1, np.int64)
    h_enq = np.zeros(len(ENQ_BINS_US) - 1, np.int64)
    enq_max = 0.0
    blocks = []
    by_strategy = defaultdict(lambda: {"cycles": 0, "stopped": 0, "learned_rows": 0, "learned_untrusted": 0,
                                       "qp_relaxed": 0, "qp_failed": 0, "limit_conflict": 0, "ssm_reduced": 0})
    for d in runs:
        c = H.cycles(d)
        cfg = H.config(d)
        strat = cfg.get("control", {}).get("strategy", "proposed")
        m = c["mode"].astype(np.int64)
        mode_counts += np.bincount(m, minlength=8)[:8]
        for name in H.FLAGS:
            flags[name] += int(H.flag(c, name).sum())
        n += len(c)
        if "cond_mask" in c.dtype.names:
            s, fl, na = composed(c["cond_mask"])
            multi += int((na > 1).sum())
            stricter += int(((s < SCALE_BY_COND[m] - 1e-12) | (fl > FLOOR_BY_COND[m] + 1e-12)).sum())
        est_ok = ~H.flag(c, "estimate_unavailable") & (c["min_sep_m"] > -1)
        sep = c["min_sep_m"][est_ok].astype(np.float64)
        h_sep += hist(sep, SEP_BINS_M)
        if "gt_min_sep_m" in c.dtype.names:
            h_gt += hist(c["gt_min_sep_m"], SEP_BINS_M)
        if "est_err_closest_m" in c.dtype.names:
            ec = c["est_err_closest_m"].astype(np.float64)
            ec = ec[np.isfinite(ec)]
            err_n += len(ec)
            err_old += int((ec > OLD_ZD).sum())
            h_err += hist(ec, ERR_BINS_M)
        e = H.exec_ms(c)
        inj = H.flag(c, "injected_overrun")
        ok = ~inj & np.isfinite(e)
        h_exec += hist(e[ok], EXEC_BINS_MS)
        if "d_enqueue_prev_ns" in c.dtype.names and len(c) > 1:
            enq = c["d_enqueue_prev_ns"][1:].astype(np.float64) * 1e-3  # enqueue of record i, stored in record i+1
            enq = enq[~inj[:-1]]
            h_enq += hist(enq, ENQ_BINS_US)
            enq_max = max(enq_max, float(enq.max()) if len(enq) else 0.0)
        a = c["human_age_ms"]
        h_age += hist(a[a >= 0], AGE_BINS_MS)
        st = by_strategy[strat]
        st["cycles"] += len(c)
        st["stopped"] += int(np.isin(m, STOP_MODES).sum())
        lu = H.flag(c, "learned_untrusted")
        if strat == "proposed":
            live = ~lu & ~H.flag(c, "stop_commanded") & ~H.flag(c, "estimate_unavailable")
            st["learned_rows"] += int(live.sum())
        st["learned_untrusted"] += int(lu.sum())
        for k in ("qp_relaxed", "qp_failed", "limit_conflict", "ssm_reduced"):
            st[k] += int(H.flag(c, k).sum())
        if per_block:
            miss = H.deadline_miss(c, H.period_ns(d))
            blocks.append({"run": d.name, "variant": cfg.get("variant"), "scenario": cfg.get("scenario_id"),
                           "load_duty": cfg.get("background_load", {}).get("duty"),
                           "cycles": int(len(c)), "exec_median_ms": float(np.median(e[ok])),
                           "exec_p99_ms": float(np.percentile(e[ok], 99)), "exec_max_ms": float(e[ok].max()),
                           "injected_overrun_cycles": int(inj.sum()),
                           "misses_retained": int((miss & ~inj).sum()),
                           "age_max_ms": float(a[a >= 0].max()) if (a >= 0).any() else None,
                           "min_sep_m": float(sep.min()) if len(sep) else None})
    enq_total = int(h_enq.sum())
    enq_med = None
    if enq_total:
        cdf = np.cumsum(h_enq) / enq_total
        enq_med = float(ENQ_BINS_US[np.searchsorted(cdf, 0.5) + 1])
    out = {"runs": len(runs), "cycles": int(n),
           "mode_fraction": {H.MODES[i]: float(mode_counts[i] / n) for i in range(8)},
           "flag_counts": dict(flags),
           "cycles_more_than_one_condition": int(multi),
           "cycles_composed_limits_stricter_than_mode": int(stricter),
           "estimate_error_closest_matched": int(err_n),
           "estimate_error_closest_above_0_04m": int(err_old),
           "enqueue_us": {"median_upper_bin_edge": enq_med, "max": enq_max if enq_total else None, "n": enq_total},
           "by_strategy": {k: dict(v) for k, v in by_strategy.items()},
           "hist": {"exec_bins_ms": EXEC_BINS_MS.tolist(), "exec": h_exec.tolist(),
                    "age_bins_ms": AGE_BINS_MS.tolist(), "age": h_age.tolist(),
                    "sep_bins_m": SEP_BINS_M.tolist(), "sep": h_sep.tolist(), "sep_true": h_gt.tolist(),
                    "err_bins_m": ERR_BINS_M.tolist(), "err_closest": h_err.tolist(),
                    "enq_bins_us": ENQ_BINS_US.tolist(), "enq": h_enq.tolist()}}
    if per_block:
        out["blocks"] = blocks
    return out


def ablation_runs(H, runs_root):
    rows = []
    for d in H.runs(runs_root, "ablation"):
        cfg = H.config(d)
        c = H.cycles(d)
        e = H.exec_ms(c)
        e = e[np.isfinite(e)]
        ri = H.release_interval_ms(c)
        ok = ~H.flag(c, "release_late")[1:]
        rows.append({"run": d.name, "configuration": cfg["ablation"]["configuration"], "seed": cfg["ablation"]["seed_index"],
                     "scenario": cfg.get("scenario_id"), "load": cfg["ablation"]["load"],
                     "median_ms": float(np.median(e)), "p99_ms": float(np.percentile(e, 99)), "max_ms": float(e.max()),
                     "sd_release_ms": float(ri[ok].std(ddof=1)),
                     "misses": int(H.deadline_miss(c, H.period_ns(d)).sum())})
    return rows


# ------------------------------------------------------------------------------------- S4
def code_metrics(H, runs_root):
    ds = sorted(Path(runs_root).glob("*_code_metrics"))
    if not ds:
        return None
    d = ds[-1]
    H.verify(d)

    def code(fn):
        j = json.loads((d / fn).read_text())
        return int(j.get("SUM", {}).get("code", 0))

    out = {"run": d.name, "commit": (d / "commit.txt").read_text().strip(),
           "shared_loc": code("cloc_shared.json"),
           "adapter_loc": {k: code(f"cloc_{k}.json") for k in ("ur_rtde", "kuka_fri", "abb_egm")}}
    rows = list(csv.reader(open(d / "lizard.csv")))
    ccn = [int(r[1]) for r in rows if len(r) > 6 and r[1].isdigit()]
    out["functions"] = len(ccn)
    out["ccn_mean"] = float(np.mean(ccn)) if ccn else None
    out["ccn_p95"] = float(np.percentile(ccn, 95)) if ccn else None
    out["ccn_max"] = int(max(ccn)) if ccn else None
    out["ccn_over_10"] = int(sum(c > 10 for c in ccn))
    out["tool_versions"] = (d / "tool_versions.txt").read_text().strip().splitlines()
    return out


# ------------------------------------------------------------------------------------- S5
def injection_breakdown(H, faults, runs_root):
    rows = []
    for d in H.runs(runs_root, "fault_injection"):
        sched = {int(r["index"]): r for r in csv.DictReader(open(d / "injection_schedule.csv"))}
        rr = faults._per_run(d, 2.0)[0]
        for r in rr:
            s = sched.get(int(r["param"]))
            r["burst_or_param"] = int(s["param"]) if s else None
        rows += rr
    comm = defaultdict(lambda: {"injected": 0, "detected": 0})
    lunge = {"injected": 0, "floor_crossed_latched": 0, "floor_held": 0, "while_stopped": 0}
    for r in rows:
        if r["category"] == "hardware_communication":
            k = r.get("burst_or_param")
            comm[str(k)]["injected"] += 1
            comm[str(k)]["detected"] += int(r["detected"])
        if r["category"] == "constraint_violation":
            lunge["injected"] += 1
            if r["detected"]:
                lunge["floor_crossed_latched"] += 1
            elif r["mode_at_injection"] in STOP_MODES:
                lunge["while_stopped"] += 1
            else:
                lunge["floor_held"] += 1
    return {"comm_by_param": dict(comm), "lunge": lunge}


def logger_drops(H, runs_root):
    n = cd = ed = 0
    for d in H.runs(runs_root):
        m = H.manifest(d)
        if "cycles_dropped_by_logger" not in m:
            continue
        n += 1
        cd += int(m.get("cycles_dropped_by_logger") or 0)
        ed += int(m.get("events_dropped_by_logger") or 0)
    return {"runs": n, "cycles_dropped": cd, "events_dropped": ed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--results", default="")
    ap.add_argument("--out", default="results_extra.json")
    ap.add_argument("--skip-heavy", action="store_true", help="skip S2/S3 (timing/compare raw scans)")
    a = ap.parse_args()
    H, faults = load_repo(a.repo)
    out = {"note": "supplementary analyses (not pre-registered); same runs, same readers, no run selected or excluded"}
    out["sensitivity_by_config"] = sensitivity_by_config(H, faults, a.runs)
    out["code_metrics"] = code_metrics(H, a.runs)
    out["injection_breakdown"] = injection_breakdown(H, faults, a.runs)
    out["ablation_runs"] = ablation_runs(H, a.runs)
    out["logger_drops"] = logger_drops(H, a.runs)
    if not a.skip_heavy:
        out["timing_behaviour"] = campaign_behaviour(H, a.runs, "timing_campaign", per_block=True)
        out["compare_behaviour"] = campaign_behaviour(H, a.runs, "baseline_compare")
        out["injection_behaviour"] = campaign_behaviour(H, a.runs, "fault_injection")
    Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
