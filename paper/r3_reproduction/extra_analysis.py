#!/usr/bin/env python3
"""Supplementary analyses for manuscript R3 that are not part of the pre-registered report.

    python3 extra_analysis.py --repo /opt/work/hrc3 --runs /opt/work/hrc3/runs \
        --results /opt/work/hrc3/results/results.json --out results_extra.json

Every quantity is computed from raw run directories through the repository's own readers
(analysis/hrc_logs.py), which verify each run's SHA-256 manifest before reading it. Nothing is
read from the manuscript. The analyses are labelled "supplementary" in the paper because they
were specified after the campaigns had been frozen (they describe the same runs in more detail;
they do not select, filter or re-weight any run):

  S1  fault_sensitivity broken down by configuration (arrival model x rate scale), using the
      pre-registered function analysis/faults.analyse applied to one run at a time;
  S2  behaviour of the safety layer over the timing and comparison campaigns: occupancy of each
      supervisor mode, use of the learned rows, relaxed and failed QP solves, separation margins;
  S3  per-block timing summaries and pooled histograms (for the figures);
  S4  code metrics (cloc / lizard) of the run directory written by tools/code_metrics.sh;
  S5  injection rows split by injected parameter (communication faults: length of the corrupt
      burst; lunges: whether the separation floor was crossed), from results.json rows.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

STOP_MODES = (5, 6, 7)
FLOOR_BY_MODE = [0.15, 0.225, 0.15, 0.30, 0.15, 0.15, 0.15, 0.15]  # include/hrc/supervisor.hpp
EXEC_BINS_MS = np.concatenate([np.arange(0, 1, 0.005), np.arange(1, 10, 0.05), np.arange(10, 60.5, 0.5)])
AGE_BINS_MS = np.arange(0, 200.5, 0.5)
SEP_BINS_M = np.arange(-0.2, 3.0001, 0.005)


def load_repo(repo):
    sys.path.insert(0, str(Path(repo) / "analysis"))
    import faults  # noqa: E402
    import hrc_logs as H  # noqa: E402
    return H, faults


def hist(x, bins):
    h, _ = np.histogram(np.clip(x, bins[0], bins[-1] - 1e-9), bins=bins)
    return h.astype(int).tolist()


# ------------------------------------------------------------------------------------- S1
def sensitivity_by_config(H, faults, runs_root):
    out = []
    for d in H.runs(runs_root, "fault_sensitivity"):
        cfg = H.config(d)["faults"]
        res = _analyse_single(H, faults, d)
        rel = res["reliability"]
        out.append({"run": d.name, "variant": H.config(d)["variant"], "arrival": cfg.get("arrival"),
                    "weibull_shape": cfg.get("weibull_shape"), "mean_cluster_size": cfg.get("mean_cluster_size"),
                    "rate_scale": cfg.get("rate_scale"),
                    "injected": sum(v["injected"] for v in res["per_category"].values()),
                    "detected": sum(v["detected"] for v in res["per_category"].values()),
                    "availability": res["availability"]["availability"],
                    "throughput_weighted": res["availability"]["throughput_weighted"],
                    "exposure_h": rel["exposure_h"],
                    "service_affecting_events": rel["service_affecting_events"],
                    "operator_intervention_events": rel["operator_intervention_events"],
                    "rate_service_affecting_per_h": rel["rate_service_affecting_per_h"],
                    "rate_ci95": rel["rate_ci95"],
                    "detection_ms_median": res["detection_ms_all"]["median"]})
    return out


def _analyse_single(H, faults, run_dir):
    """faults.analyse restricted to one run directory, without modifying the analysis code:
    temporarily replace H.runs so that it yields exactly this directory."""
    orig = faults.H.runs
    try:
        faults.H.runs = lambda root, exp=None, include_incomplete=False: [run_dir]
        return faults.analyse(str(run_dir.parent), ("fault_sensitivity",))
    finally:
        faults.H.runs = orig


# ------------------------------------------------------------------------------------- S2, S3
def campaign_behaviour(H, runs_root, experiment, per_block=False):
    runs = H.runs(runs_root, experiment)
    if not runs:
        return None
    mode_counts = np.zeros(8, dtype=np.int64)
    flags = Counter()
    n = 0
    n_est = 0
    below_floor = 0
    below_viol = 0
    sep_min = np.inf
    h_exec = np.zeros(len(EXEC_BINS_MS) - 1, dtype=np.int64)
    h_age = np.zeros(len(AGE_BINS_MS) - 1, dtype=np.int64)
    h_sep = np.zeros(len(SEP_BINS_M) - 1, dtype=np.int64)
    blocks = []
    by_strategy = defaultdict(lambda: {"cycles": 0, "stopped": 0, "learned_rows": 0, "learned_untrusted": 0,
                                       "qp_relaxed": 0, "qp_failed": 0})
    for d in runs:
        c = H.cycles(d)
        cfg = H.config(d)
        strat = cfg["control"]["strategy"]
        m = c["mode"].astype(np.int64)
        mode_counts += np.bincount(m, minlength=8)[:8]
        for name in H.FLAGS:
            flags[name] += int(H.flag(c, name).sum())
        n += len(c)
        avail = ~H.flag(c, "estimate_unavailable") & (c["min_sep_m"] > -1)
        n_est += int(avail.sum())
        sep = c["min_sep_m"][avail].astype(np.float64)
        floor = np.asarray(FLOOR_BY_MODE)[m[avail]]
        below_floor += int((sep < floor).sum())
        below_viol += int((sep < floor - 0.05).sum())
        if len(sep):
            sep_min = min(sep_min, float(sep.min()))
            h_sep += np.asarray(hist(sep, SEP_BINS_M))
        e = H.exec_ms(c)
        inj = H.flag(c, "injected_overrun")
        h_exec += np.asarray(hist(e[~inj], EXEC_BINS_MS))
        a = c["human_age_ms"]
        h_age += np.asarray(hist(a[a >= 0], AGE_BINS_MS))
        s = by_strategy[strat]
        s["cycles"] += len(c)
        s["stopped"] += int(np.isin(m, STOP_MODES).sum())
        lu = H.flag(c, "learned_untrusted")
        if strat == "proposed":
            live = ~lu & ~H.flag(c, "stop_commanded") & ~H.flag(c, "estimate_unavailable")
            s["learned_rows"] += int(live.sum())
        s["learned_untrusted"] += int(lu.sum())
        s["qp_relaxed"] += int(H.flag(c, "qp_relaxed").sum())
        s["qp_failed"] += int(H.flag(c, "qp_failed").sum())
        if per_block:
            ok = ~inj
            blocks.append({"run": d.name, "variant": cfg["variant"], "scenario": cfg.get("scenario_id"),
                           "load_duty": cfg.get("background_load", {}).get("duty"),
                           "cycles": int(len(c)), "exec_median_ms": float(np.median(e[ok])),
                           "exec_p99_ms": float(np.percentile(e[ok], 99)), "exec_max_ms": float(e[ok].max()),
                           "injected_overrun_cycles": int(inj.sum()),
                           "misses_retained": int((H.flag(c, "overrun") & ok).sum()),
                           "age_max_ms": float(a[a >= 0].max()) if (a >= 0).any() else None,
                           "min_sep_m": float(sep.min()) if len(sep) else None})
    out = {"runs": len(runs), "cycles": int(n),
           "mode_fraction": {H.MODES[i]: float(mode_counts[i] / n) for i in range(8)},
           "flag_counts": dict(flags),
           "cycles_with_estimate": n_est,
           "cycles_below_active_floor": below_floor,
           "cycles_below_floor_by_more_than_0_05m": below_viol,
           "min_separation_m": None if sep_min == np.inf else sep_min,
           "by_strategy": {k: dict(v) for k, v in by_strategy.items()},
           "hist": {"exec_bins_ms": EXEC_BINS_MS.tolist(), "exec": h_exec.tolist(),
                    "age_bins_ms": AGE_BINS_MS.tolist(), "age": h_age.tolist(),
                    "sep_bins_m": SEP_BINS_M.tolist(), "sep": h_sep.tolist()}}
    if per_block:
        out["blocks"] = blocks
    return out


def ablation_runs(H, runs_root):
    rows = []
    for d in H.runs(runs_root, "ablation"):
        cfg = H.config(d)
        c = H.cycles(d)
        e = H.exec_ms(c)
        ri = H.release_interval_ms(c)
        ok = ~H.flag(c, "release_late")[1:]
        rows.append({"run": d.name, "configuration": cfg["ablation"]["configuration"], "seed": cfg["ablation"]["seed_index"],
                     "scenario": cfg.get("scenario_id"), "load": cfg["ablation"]["load"],
                     "median_ms": float(np.median(e)), "p99_ms": float(np.percentile(e, 99)), "max_ms": float(e.max()),
                     "sd_release_ms": float(ri[ok].std(ddof=1)), "misses": int(H.flag(c, "overrun").sum())})
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
    # lizard --csv columns: NLOC, CCN, token, PARAM, length, location, file, function, long_name, start, end
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
    """Rows of faults._per_run (the pre-registered matching), joined with each run's
    injection_schedule.csv so that the injected parameter is known (the event log stores the
    schedule index as `detail`)."""
    rows = []
    for d in H.runs(runs_root, "fault_injection"):
        sched = {int(r["index"]): r for r in csv.DictReader(open(d / "injection_schedule.csv"))}
        rr = faults._per_run(d, 2.0)[0]
        for r in rr:
            s = sched.get(int(r["param"]))
            r["burst_or_param"] = int(s["param"]) if s else None
            r["duration_s"] = float(s["duration_s"]) if s else None
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
    """Records dropped by the real-time logger (ring full), summed over every complete run."""
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
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", default="results_extra.json")
    ap.add_argument("--skip-heavy", action="store_true", help="skip S2/S3 (timing/compare raw scans)")
    a = ap.parse_args()
    H, faults = load_repo(a.repo)
    results = json.loads(Path(a.results).read_text()) if Path(a.results).exists() else {}
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
