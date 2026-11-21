#!/usr/bin/env python3
"""Generate every number and every data table of manuscript R4 (release 3.1, campaigns v4).

    python3 make_numbers.py --results data/results.json --extra data/results_extra.json \
        --results-r30 data_r30/results.json --stop-summary data/stop_check_summary.txt \
        --stop-csv data/stop_check_compare.csv --out numbers

Inputs
  results.json            analysis/report.py at tag campaign-v4-report (pre-registered analysis)
  results_extra.json      scripts/extra_analysis.py (supplementary)
  results_r30.json        results.json of release 3.0 (tag campaign-v3-report); used ONLY for the two
                          retained results: URSim conformance and the held-out barrier network
  stop_check_summary.txt  stderr of tools/stop_check (written by queue4.sh)
  stop_check_compare.csv  per-sample output of tools/stop_check
Outputs (in --out)
  r4_numbers.tex      one \\newcommand per number used in the text (prefix R)
  tab_*.tex           table bodies (rows only); the table frames live in the manuscript
  provenance.txt      SHA-256 of the inputs

No number is written here by hand: a quantity that is absent from the inputs prints as a red
"??" (\\missingnum), so a missing result cannot go unnoticed in the compiled PDF.
"""
import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

MISSING = r"\missingnum"
CATS = [("tracking_loss", "Tracking loss"), ("sensor_timeout", "Sensor timeout (one stream)"),
        ("computational_overrun", "Computational overrun"), ("hardware_communication", "Hardware communication"),
        ("configuration_inconsistency", "Configuration inconsistency"), ("network_partition", "Network partition"),
        ("constraint_violation", "Constraint violation (lunge)"), ("memory_allocation", "Memory allocation")]
ABL = [("A0", "A0 static dispatch"), ("A1", "A1 socket transport"), ("A2a", "A2a no RT priority"),
       ("A2b", "A2b shared core"), ("A2c", "A2c no watchdog"), ("A2", "A2 all three removed"), ("A3", "A3 full")]
STRATS = ("proposed", "hc_cbf", "ssm", "pf_ssm", "pf")
BASELINES = ("hc_cbf", "ssm", "pf_ssm", "pf")
STRAT = {"proposed": "Proposed (geometric + learned CBF-QP)", "hc_cbf": "HC-CBF (geometric CBF-QP)",
         "ssm": "SSM (ISO/TS 15066 speed limit)", "pf_ssm": "PF-SSM (potential field + SSM limit)",
         "pf": "PF (potential field, no SSM limit)"}
STRAT_SHORT = {"proposed": "Proposed", "hc_cbf": "HC-CBF", "ssm": "SSM", "pf_ssm": "PF-SSM", "pf": "PF"}
KEY = {"hc_cbf": "HCCBF", "ssm": "SSM", "pf_ssm": "PFSSM", "pf": "PF", "proposed": "Prop"}
PARAM_TEX = {"control.kappa": r"$\kappa$ (s$^{-1}$)", "ssm.C": r"$C$ (m)", "pf.k_rep": r"$k_{\mathrm{rep}}$"}
CAMPAIGNS = (("timing_campaign", "Timing", "Tim"), ("baseline_compare", "Comparison", "Cmp"),
             ("fault_injection", "Fault injection", "Inj"))


# ------------------------------------------------------------------------------- helpers
def get(d, path, default=None):
    """Dotted path; '*' selects the first (sorted) key of a run-keyed dict."""
    cur = d
    for k in path.split("."):
        if cur is None:
            return default
        if k == "*":
            if not isinstance(cur, dict) or not cur:
                return default
            cur = cur[sorted(cur)[0]]
        elif isinstance(cur, dict):
            cur = cur.get(k)
        elif isinstance(cur, list) and k.isdigit():
            i = int(k)
            cur = cur[i] if i < len(cur) else None
        else:
            return default
    return default if cur is None else cur


def ok(v):
    return v is not None and not isinstance(v, (dict, list)) and not (
        isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def f(v, nd=2, scale=1.0):
    if not ok(v):
        return MISSING
    return f"{float(v) * scale:,.{nd}f}".replace(",", "{,}")


def fi(v):
    if not ok(v):
        return MISSING
    return f"{int(round(float(v))):,}".replace(",", "{,}")


def fsig(v, sig=3, scale=1.0):
    """Significant figures, no exponent for 1e-3..1e5."""
    if not ok(v):
        return MISSING
    x = float(v) * scale
    if x == 0:
        return "0"
    a = abs(x)
    if 1e-3 <= a < 1e5:
        nd = max(0, sig - 1 - int(math.floor(math.log10(a))))
        return f"{x:,.{nd}f}".replace(",", "{,}")
    m, e = f"{x:.{sig - 1}e}".split("e")
    return rf"\ensuremath{{{m}\times10^{{{int(e)}}}}}"


def fp(v):
    if not ok(v):
        return MISSING
    v = float(v)
    return r"$<$0.001" if v < 0.001 else f"{v:.3f}"


def fci(lo, hi, nd=2, scale=1.0):
    if not (ok(lo) and ok(hi)):
        return MISSING
    return f"[{f(lo, nd, scale)}, {f(hi, nd, scale)}]"


def fpct(num, den, nd=2):
    if not (ok(num) and ok(den)) or float(den) == 0:
        return MISSING
    return f(float(num) / float(den), nd, 100)


def poisson_ci(k, t, alpha=0.05):
    """Exact (Garwood) interval for a Poisson rate k/t, by bisection on the Poisson CDF."""
    if not (ok(k) and ok(t)) or t <= 0:
        return (None, None)
    k = int(k)

    def cdf(kk, mu):  # P(X <= kk)
        if kk < 0:
            return 0.0
        term = math.exp(-mu)
        s = term
        for i in range(1, kk + 1):
            term *= mu / i
            s += term
        return s

    def root_increasing(fun, target):  # fun increasing in mu
        lo, hi = 0.0, max(10.0, 10.0 * (k + 1))
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if fun(mid) < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    # lower limit: P(X >= k | mu) = alpha/2; upper limit: P(X <= k | mu) = alpha/2
    lower = 0.0 if k == 0 else root_increasing(lambda mu: 1 - cdf(k - 1, mu), alpha / 2)
    upper = root_increasing(lambda mu: 1 - cdf(k, mu), 1 - alpha / 2)
    return (lower / t, upper / t)


class Macros:
    def __init__(self):
        self.m = {}

    def __setitem__(self, k, v):
        assert k.isalpha(), k
        self.m[k] = v if v is not None else MISSING

    def tex(self, header):
        out = [header, r"\providecommand{\missingnum}{\textcolor{red}{??}}"]
        for k in sorted(self.m):
            out.append(f"\\newcommand{{\\{k}}}{{{typeset_minus(self.m[k])}}}")
        return "\n".join(out) + "\n"


_NEG = re.compile(r"(?<![A-Za-z0-9\-{])-(?=\d)")


def typeset_minus(v):
    """Print a negative number with a true minus sign (text or math mode), not a hyphen."""
    return _NEG.sub(r"\\ensuremath{-}", v) if isinstance(v, str) else v


def row(*cells):
    return " & ".join(cells) + r" \\"


# ------------------------------------------------------------------------------- timing, ablation
def timing(res, extra, M, T):
    t = res.get("timing") or {}
    M["RTimRuns"] = fi(get(t, "runs"))
    M["RTimCyclesTotal"] = fi(get(t, "cycles.total"))
    M["RTimCyclesInj"] = fi(get(t, "cycles.with_injected_overrun_excluded"))
    M["RTimCyclesRet"] = fi(get(t, "cycles.retained"))
    M["RTimMissRet"] = fi(get(t, "cycles.deadline_misses_retained"))
    M["RTimMissInj"] = fi(get(t, "cycles.deadline_misses_in_injected"))
    M["RTimLateRel"] = fi(get(t, "cycles.late_releases"))
    for k, n in (("median", "Med"), ("p95", "PNineFive"), ("p99", "PNineNine"), ("max", "Max"), ("sd", "SD")):
        M[f"RTimExec{n}"] = fsig(get(t, f"exec_ms.{k}"), 3)
        M[f"RTimExec{n}Us"] = fsig(get(t, f"exec_ms.{k}"), 3, 1000)
    M["RTimExecMedPct"] = f(get(t, "exec_ms.median"), 2, 100 / 20.0)
    M["RTimRelMean"] = f(get(t, "release_interval_ms.mean"), 3)
    M["RTimRelSDUs"] = fsig(get(t, "release_interval_ms.sd"), 2, 1000)
    names = [("state", "State read (robot + human)"), ("nominal", "Nominal controller"), ("geo", "Geometric barrier rows"),
             ("learned", "Learned barrier (forward + gradient)"), ("qp", "Limited QP (speed limits inside) + final check"),
             ("dispatch", "Command dispatch"), ("log", "Record construction")]
    rows = []
    for k, label in names:
        v = get(t, f"stage_median_ms.{k}")
        M["RTimStage" + k.capitalize() + "Us"] = fsig(v, 3, 1000)
        rows.append(row(label, fsig(v, 3, 1000)))
    enq = get(extra, "timing_behaviour.enqueue_us", {}) or {}
    M["RTimEnqMedUs"] = fsig(enq.get("median_upper_bin_edge"), 2)
    M["RTimEnqMaxUs"] = fsig(enq.get("max"), 3)
    rows.append(row("Enqueue of the record (median, supplementary)", fsig(enq.get("median_upper_bin_edge"), 2)))
    T["tab_stages"] = rows
    M["RTimAgeMed"] = f(get(t, "estimate_age_ms.median"), 1)
    M["RTimAgePNineFive"] = f(get(t, "estimate_age_ms.p95"), 1)
    M["RTimAgeMax"] = f(get(t, "estimate_age_ms.max"), 1)
    am = get(t, "estimate_age_ms.median")
    M["RSageMedMm"] = f(am * (1.6 + 0.3), 0) if ok(am) else MISSING  # (v_h + v_r) t_age at v_r = 0.3 m/s, mm
    M["RTimBlocks"] = fi(get(t, "blocks.n"))
    M["RTimBlocksMiss"] = fi(get(t, "blocks.with_retained_miss"))
    ub = get(t, "blocks.upper95_p_block_has_miss")
    M["RTimBlockBound"] = fsig(ub, 2)
    M["RTimBlockBoundPct"] = f(ub, 1, 100)
    M["RTimExclNonRT"] = fi(len(get(t, "excluded_non_rt", []) or []) if t else None)
    blocks = get(extra, "timing_behaviour.blocks", []) or []
    if blocks:
        mx = sorted(b["exec_max_ms"] for b in blocks)
        M["RBlkMaxMedian"] = f(mx[len(mx) // 2], 2)
        M["RBlkMaxMax"] = f(mx[-1], 2)
        M["RBlkOverOne"] = fi(sum(1 for x in mx if x > 1.0))
        M["RBlkOverTen"] = fi(sum(1 for x in mx if x > 10.0))
        r = sorted(b["exec_max_ms"] / b["exec_p99_ms"] for b in blocks)
        M["RBlkMaxToPNineNine"] = f(r[len(r) // 2], 1)
        xs = [b["load_duty"] for b in blocks if b.get("load_duty") is not None]
        ys = [b["exec_max_ms"] for b in blocks if b.get("load_duty") is not None]
        if len(xs) > 2:
            n = len(xs); mxv = sum(xs) / n; myv = sum(ys) / n
            cov = sum((a - mxv) * (b - myv) for a, b in zip(xs, ys))
            sx = math.sqrt(sum((a - mxv) ** 2 for a in xs)); sy = math.sqrt(sum((b - myv) ** 2 for b in ys))
            M["RBlkMaxLoadCorr"] = f(cov / (sx * sy), 2) if sx and sy else MISSING
    for k in ("RBlkMaxMedian", "RBlkMaxMax", "RBlkOverOne", "RBlkOverTen", "RBlkMaxToPNineNine", "RBlkMaxLoadCorr"):
        if k not in M.m:
            M[k] = MISSING


def ablation(res, extra, M, T):
    a = get(res, "ablation.configurations", {}) or {}
    rows = []
    misses = []
    for k, label in ABL:
        c = a.get(k, {}) or {}
        ci = c.get("median_ci95_over_run_medians", [None, None]) or [None, None]
        nd = 3
        rows.append(row(label, fi(c.get("runs")), fi(c.get("cycles")), f(c.get("median_ms"), nd),
                        fci(ci[0], ci[1], nd), f(c.get("p95_ms"), nd), f(c.get("p99_ms"), nd), f(c.get("max_ms"), 2),
                        f(c.get("sd_exec_ms"), nd), f(c.get("sd_release_interval_ms"), nd), f(c.get("miss_pct"), 3)))
        key = k.replace("2a", "Twoa").replace("2b", "Twob").replace("2c", "Twoc").replace("0", "Zero") \
               .replace("1", "One").replace("2", "Two").replace("3", "Three")
        M[f"RAbl{key}Max"] = f(c.get("max_ms"), 2)
        M[f"RAbl{key}PNineNine"] = f(c.get("p99_ms"), 3)
        if ok(c.get("miss_pct")) and c.get("miss_pct") > 0:
            misses.append((k, c.get("miss_pct")))
    T["tab_ablation"] = rows
    M["RAblCyclesTotal"] = fi(sum((a.get(k, {}) or {}).get("cycles", 0) or 0 for k, _ in ABL)) if a else MISSING
    M["RAblRuns"] = fi(sum((a.get(k, {}) or {}).get("runs", 0) or 0 for k, _ in ABL)) if a else MISSING
    M["RAblExcluded"] = fi(len(get(res, "ablation.notes", []) or [])) if a else MISSING
    if a:
        M["RAblMissText"] = ("No configuration missed a deadline." if not misses else
                             "Deadline misses occurred in " + ", ".join(f"{k} ({f(p, 3)}\\% of cycles)" for k, p in misses) + ".")
    else:
        M["RAblMissText"] = MISSING
    if a and "A0" in a and "A3" in a:
        M["RAblAThreeMinusAZeroUs"] = fsig(a["A3"]["median_ms"] - a["A0"]["median_ms"], 2, 1000)
        M["RAblAOneMinusAThreeUs"] = fsig(a["A1"]["median_ms"] - a["A3"]["median_ms"], 3, 1000) if "A1" in a else MISSING
    else:
        M["RAblAThreeMinusAZeroUs"] = M["RAblAOneMinusAThreeUs"] = MISSING
    ar = (extra or {}).get("ablation_runs") or []
    keys = ("RAblIdleMedMinUs", "RAblIdleMedMaxUs", "RAblLoadMedMinUs", "RAblLoadMedMaxUs", "RAblATwoLoadMaxMed",
            "RAblATwoLoadMax", "RAblATwoLoadSDRelUs", "RAblAThreeLoadSDRelUs", "RAblAThreeLoadMax", "RAblATwoIdleMax",
            "RAblAThreeIdleMax")
    if not ar:
        for k in keys:
            M[k] = MISSING
        return

    def med(v):
        v = sorted(v); n = len(v)
        return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])
    by = {}
    for r in ar:
        by.setdefault((r["configuration"], r["load"]), []).append(r)
    idle = {c: med([r["median_ms"] for r in by[(c, "idle")]]) for c, _ in ABL if (c, "idle") in by and c != "A1"}
    load = {c: med([r["median_ms"] for r in by[(c, "load")]]) for c, _ in ABL if (c, "load") in by and c != "A1"}
    M["RAblIdleMedMinUs"] = fi(1000 * min(idle.values())) if idle else MISSING
    M["RAblIdleMedMaxUs"] = fi(1000 * max(idle.values())) if idle else MISSING
    M["RAblLoadMedMinUs"] = fi(1000 * min(load.values())) if load else MISSING
    M["RAblLoadMedMaxUs"] = fi(1000 * max(load.values())) if load else MISSING

    def mx(c, l):
        return max(r["max_ms"] for r in by[(c, l)]) if (c, l) in by else None

    def medmx(c, l):
        return med([r["max_ms"] for r in by[(c, l)]]) if (c, l) in by else None

    def sdr(c, l):
        return med([r["sd_release_ms"] for r in by[(c, l)]]) if (c, l) in by else None
    M["RAblATwoLoadMaxMed"] = f(medmx("A2", "load"), 2)
    M["RAblATwoLoadMax"] = f(mx("A2", "load"), 2)
    M["RAblATwoLoadSDRelUs"] = fi(1000 * sdr("A2", "load")) if sdr("A2", "load") is not None else MISSING
    M["RAblAThreeLoadSDRelUs"] = fi(1000 * sdr("A3", "load")) if sdr("A3", "load") is not None else MISSING
    M["RAblAThreeLoadMax"] = f(mx("A3", "load"), 2)
    M["RAblATwoIdleMax"] = f(mx("A2", "idle"), 2)
    M["RAblAThreeIdleMax"] = f(mx("A3", "idle"), 2)


# ------------------------------------------------------------------------------- faults, availability
SHORT = {"tracking_loss": "Track", "sensor_timeout": "Stream", "computational_overrun": "Overrun",
         "hardware_communication": "Comm", "configuration_inconsistency": "Config", "network_partition": "Part",
         "constraint_violation": "Lunge", "memory_allocation": "Mem"}


def faults_section(res, prefix, key, M, T, table_name=None, rel_table=None):
    fr = res.get(key) or {}
    M[f"R{prefix}Runs"] = fi(get(fr, "runs"))
    pc = get(fr, "per_category", {}) or {}

    def tot(k):
        return sum(v.get(k, 0) or 0 for v in pc.values()) if pc else None
    M[f"R{prefix}Injected"] = fi(tot("injected"))
    M[f"R{prefix}Detected"] = fi(tot("detected"))
    M[f"R{prefix}UndStopped"] = fi(tot("undetected_while_stopped"))
    M[f"R{prefix}UndAbsorbed"] = fi(tot("undetected_absorbed_in_ongoing_episode"))
    M[f"R{prefix}UndOther"] = fi(tot("undetected_other"))
    M[f"R{prefix}Ambiguous"] = fi(tot("ambiguous_or_overlapping"))
    M[f"R{prefix}DetMed"] = f(get(fr, "detection_ms_all.median"), 0)
    M[f"R{prefix}DetPNineFive"] = f(get(fr, "detection_ms_all.p95"), 0)
    M[f"R{prefix}DetMax"] = f(get(fr, "detection_ms_all.max"), 0)
    for k, n in SHORT.items():
        c = pc.get(k) or {}
        M[f"R{prefix}DetMed{n}"] = f(c.get("detection_ms_median"), 0)
        M[f"R{prefix}DetMax{n}"] = f(c.get("detection_ms_max"), 0)
    M[f"R{prefix}RecConfig"] = fsig(get(pc, "configuration_inconsistency.recovery_s_median"), 2)
    av = get(fr, "availability", {}) or {}
    M[f"R{prefix}AvOutside"] = f(av.get("outside_stop_modes"), 2, 100)
    M[f"R{prefix}AvPermitted"] = f(av.get("motion_permitted"), 2, 100)
    M[f"R{prefix}AvDiff"] = f(av.get("difference_controller_stops"), 3, 100)
    M[f"R{prefix}AvScale"] = f(av.get("mean_speed_scale_proxy"), 1, 100)
    M[f"R{prefix}AvUnrecS"] = f(av.get("unrecorded_s"), 1)
    r = "reliability."
    M[f"R{prefix}ExposureH"] = f(get(fr, r + "exposure_h"), 1)
    M[f"R{prefix}SAEvents"] = fi(get(fr, r + "service_affecting_events"))
    M[f"R{prefix}OpEvents"] = fi(get(fr, r + "operator_intervention_events"))
    M[f"R{prefix}SARate"] = fsig(get(fr, r + "rate_service_affecting_per_h"), 3)
    M[f"R{prefix}SARateCI"] = fci(get(fr, r + "rate_ci95_poisson_exact.0"), get(fr, r + "rate_ci95_poisson_exact.1"), 2)
    M[f"R{prefix}SARateBootCI"] = fci(get(fr, r + "rate_ci95_run_bootstrap.0"), get(fr, r + "rate_ci95_run_bootstrap.1"), 2)
    M[f"R{prefix}OpRate"] = fsig(get(fr, r + "rate_operator_per_h"), 3)
    M[f"R{prefix}OpRateCI"] = fci(get(fr, r + "rate_operator_ci95_poisson_exact.0"),
                                  get(fr, r + "rate_operator_ci95_poisson_exact.1"), 3)
    M[f"R{prefix}OpRateBootCI"] = fci(get(fr, r + "rate_operator_ci95_run_bootstrap.0"),
                                      get(fr, r + "rate_operator_ci95_run_bootstrap.1"), 3)
    di = get(fr, r + "dispersion_across_runs", {}) or {}
    M[f"R{prefix}DispIndex"] = f(di.get("index"), 2)
    M[f"R{prefix}DispP"] = fp(di.get("p_overdispersion"))
    pdi = di.get("p_overdispersion")
    if ok(pdi):
        M[f"R{prefix}DispText"] = ("so the counts vary between blocks more than a Poisson process allows, and the run-bootstrap "
                                   "interval, which does not assume independent events, is the one to read."
                                   if pdi < 0.05 else
                                   "which does not indicate more variation between blocks than a Poisson process allows; "
                                   "both intervals are given.")
    else:
        M[f"R{prefix}DispText"] = MISSING
    M[f"R{prefix}IntComplete"] = fi(get(fr, r + "intervals.complete"))
    M[f"R{prefix}IntCensored"] = fi(get(fr, r + "intervals.censored"))
    q = get(fr, r + "complete_intervals_h_quantiles", {}) or {}
    M[f"R{prefix}IntMedH"] = fsig(q.get("50"), 3)
    M[f"R{prefix}IntQOneH"] = fsig(q.get("25"), 3)
    M[f"R{prefix}IntQThreeH"] = fsig(q.get("75"), 3)
    w = get(fr, r + "weibull_descriptive", {}) or {}
    M[f"R{prefix}WeibullShape"] = f(w.get("shape"), 2)
    M[f"R{prefix}WeibullScale"] = fsig(w.get("scale_h"), 3)
    M[f"R{prefix}WeibullGofP"] = fp(get(w, "gof_parametric_bootstrap.p_value"))
    M[f"R{prefix}WeibullGofN"] = fi(get(w, "gof_parametric_bootstrap.replicates"))
    if table_name:
        rows = []
        for k, label in CATS:
            c = pc.get(k) or {}
            if not pc:
                rows.append(row(label, *([MISSING] * 11)))
                continue
            dash = lambda v, fn: fn(v) if v is not None else "--"
            rows.append(row(label, fi(c.get("injected", 0)), fi(c.get("detected", 0)),
                            fi(c.get("undetected_while_stopped", 0)), fi(c.get("undetected_absorbed_in_ongoing_episode", 0)),
                            fi(c.get("undetected_other", 0)), fi(c.get("ambiguous_or_overlapping", 0)),
                            dash(c.get("detection_ms_median"), lambda v: f(v, 0)),
                            dash(c.get("detection_ms_max"), lambda v: f(v, 0)),
                            dash(c.get("recovery_s_median"), lambda v: fsig(v, 2)),
                            fi(c.get("recovery_censored", 0)),
                            "yes" if c.get("operator_intervention_class") else "no"))
        T[table_name] = rows
    if rel_table:
        rows = []
        per = get(fr, r + "per_category", {}) or {}
        hours = get(fr, r + "exposure_h")
        for k, label in CATS:
            label = label.replace(" (lunge)", "")  # episodes include violations not caused by an injected lunge
            if not fr:
                rows.append(row(label, MISSING, MISSING, MISSING))
                continue
            if k == "configuration_inconsistency":
                rows.append(row(label, "n/a", "n/a", "n/a"))
                continue
            c = per.get(k)
            ev = c["events"] if c else 0
            lo, hi = poisson_ci(ev, hours)
            rows.append(row(label, fi(ev), fsig(ev / hours, 3) if ok(hours) and hours > 0 else MISSING, fci(lo, hi, 3)))
        T[rel_table] = rows


def sensitivity_table(extra, M, T):
    rows = []
    sc = (extra or {}).get("sensitivity_by_config") or []
    order = {"poisson": 0, "clustered": 1, "weibull": 2}
    name = lambda s: ("Poisson" if s["arrival"] == "poisson" else "Clustered (Neyman--Scott)" if s["arrival"] == "clustered"
                      else f"Weibull renewal, $k={s['weibull_shape']}$")
    for s in sorted(sc, key=lambda s: (order.get(s["arrival"], 9), s.get("weibull_shape") or 0, s["rate_scale"])):
        rows.append(row(name(s), f"{s['rate_scale']:.1f}", fi(s["injected"]), fi(s["service_affecting_events"]),
                        fi(s["operator_intervention_events"]), fsig(s["rate_service_affecting_per_h"], 3),
                        f(s["availability"], 1, 100), f(s["mean_speed_scale"], 1, 100)))
    T["tab_sensitivity"] = rows or [row(MISSING, *([MISSING] * 7))]
    if sc:
        av = [s["availability"] for s in sc]
        M["RSensAvailMin"] = f(min(av), 1, 100)
        M["RSensAvailMax"] = f(max(av), 1, 100)
        xs = [s["operator_intervention_events"] for s in sc]; ys = [100 * s["availability"] for s in sc]
        n = len(xs); mxv = sum(xs) / n; myv = sum(ys) / n
        sxx = sum((a - mxv) ** 2 for a in xs)
        M["RSensSlopePct"] = f(-sum((a - mxv) * (b - myv) for a, b in zip(xs, ys)) / sxx, 1) if sxx else MISSING
    else:
        M["RSensAvailMin"] = M["RSensAvailMax"] = M["RSensSlopePct"] = MISSING


# ------------------------------------------------------------------------------- tuning and comparison
def tuning_compare(res, M, T):
    sel = res.get("tuning_selection") or {}
    rows = []
    for k in STRATS:
        s = sel.get(k)
        if not s:
            rows.append(row(STRAT[k], MISSING, MISSING, MISSING, MISSING, MISSING))
            continue
        rows.append(row(STRAT[k], PARAM_TEX.get(s["parameter"], s["parameter"].replace("_", r"\_")), f"{s['value']:g}",
                        f(s["mean_task_cycle_s"], 2), fi(s["min_sep_m"] * 1000), fi(s["segments"])))
        M["RTune" + KEY[k] + "Value"] = f"{s['value']:g}"
    T["tab_tuning"] = rows
    bc = res.get("baseline_comparison") or {}
    rr = bc.get("rows") or []
    M["RCmpHypotheses"] = fi(bc.get("hypotheses"))
    rows = []
    sig = 0
    for ep, unit, scale, nd in (("task_cycle_s", "s", 1, 2), ("min_sep_m", "mm", 1000, 0)):
        for b in BASELINES:
            r = next((x for x in rr if x["endpoint"] == ep and x["baseline"] == b), None)
            epl = "Task cycle (s)" if ep == "task_cycle_s" else r"Min.\ est.\ sep.\ (mm)"
            key = ("Cyc" if ep == "task_cycle_s" else "Sep") + KEY[b]
            if not r:
                rows.append(row(epl, STRAT_SHORT[b], *([MISSING] * 6)))
                for s in ("Diff", "CI", "PHolm"):
                    M[f"RCmp{key}{s}"] = MISSING
                continue
            sig += int(r["p_holm"] < 0.05)
            rows.append(row(epl, STRAT_SHORT[b], f"{f(r['proposed_mean'], nd, scale)} $\\pm$ {f(r['proposed_sd'], nd, scale)}",
                            f"{f(r['baseline_mean'], nd, scale)} $\\pm$ {f(r['baseline_sd'], nd, scale)}",
                            f"{f(r['mean_diff'], nd, scale)} {fci(r['ci95'][0], r['ci95'][1], nd, scale)}",
                            f(r["d_z"], 2) if r.get("d_z") is not None else "--", fp(r["p"]), fp(r["p_holm"])))
            M[f"RCmp{key}Diff"] = f(r["mean_diff"], nd, scale)
            M[f"RCmp{key}CI"] = fci(r["ci95"][0], r["ci95"][1], nd, scale)
            M[f"RCmp{key}PHolm"] = fp(r["p_holm"])
    rows.append(r"\hline")
    sec = bc.get("secondary_true_separation") or []
    for b in BASELINES:
        r = next((x for x in sec if x["baseline"] == b), None)
        epl = r"Min.\ true sep.\ (mm)$^{\dagger}$"
        if not r:
            rows.append(row(epl, STRAT_SHORT[b], *([MISSING] * 4), "--", "--"))
            M[f"RCmpTrue{KEY[b]}Diff"] = MISSING
            continue
        rows.append(row(epl, STRAT_SHORT[b], f(r["proposed_mean"], 0, 1000), f(r["baseline_mean"], 0, 1000),
                        f"{f(r['mean_diff'], 0, 1000)} {fci(r['ci95'][0], r['ci95'][1], 0, 1000)}",
                        f(r["d_z"], 2) if r.get("d_z") is not None else "--", "--", "--"))
        M[f"RCmpTrue{KEY[b]}Diff"] = f(r["mean_diff"], 0, 1000)
    T["tab_compare"] = rows
    M["RCmpSignificant"] = fi(sig) if rr else MISSING


# ------------------------------------------------------------------------------- behaviour (3.1 fields)
def behaviour(res, extra, M, T):
    B = res.get("behaviour") or {}
    prop = lambda exp: (B.get(exp) or {}).get("proposed") or {}
    tim = prop("timing_campaign")
    # dispatched commands, all campaigns with the proposed controller
    allp = [prop(e) for e in B if prop(e)]
    if allp:
        M["RBehAllCycles"] = fi(sum(p["cycles"] for p in allp))
        M["RBehAllDispatched"] = fi(sum(p["dispatched_cycles"] for p in allp))
        M["RBehAllFinalViolMax"] = fsig(max(p["final_viol_max"] for p in allp), 2)
        M["RBehAllFinalFailed"] = fi(sum(p["final_check_failed"] for p in allp))
    else:
        for k in ("RBehAllCycles", "RBehAllDispatched", "RBehAllFinalViolMax", "RBehAllFinalFailed"):
            M[k] = MISSING
    M["RBehTimLimitConflict"] = fi(get(tim, "controller_stops.limit_conflict"))
    M["RBehTimQpFailed"] = fi(get(tim, "controller_stops.qp_failed"))
    M["RBehTimSsmReducedPct"] = fpct(tim.get("ssm_reduced_cycles"), tim.get("cycles"), 1)
    e = tim.get("estimate_error_closest_m") or {}
    M["RBehTimErrCloseMedMm"] = f(e.get("p50"), 0, 1000)
    M["RBehTimErrClosePNineFiveMm"] = f(e.get("p95"), 0, 1000)
    M["RBehTimErrClosePNineNineMm"] = f(e.get("p99"), 0, 1000)
    M["RBehTimErrN"] = fi(e.get("n"))
    M["RBehTimErrAboveMarginPct"] = f(tim.get("share_closest_error_above_margin"), 2, 100)
    M["RBehTimErrWorstPNineNineMm"] = f(get(tim, "estimate_error_worst_keypoint_m.p99"), 0, 1000)
    dif = tim.get("estimated_minus_true_separation_m") or {}
    M["RBehTimDifMedMm"] = f(dif.get("p50"), 0, 1000)
    M["RBehTimDifPOneMm"] = f(dif.get("p1"), 0, 1000)
    M["RBehTimDifPNineNineMm"] = f(dif.get("p99"), 0, 1000)
    M["RBehTimGtBelowEstAbove"] = fi(tim.get("true_below_floor_while_estimate_above_cycles"))
    tb = (extra or {}).get("timing_behaviour") or {}
    M["RBehTimErrAboveOldZdPct"] = fpct(tb.get("estimate_error_closest_above_0_04m"), tb.get("estimate_error_closest_matched"), 1)
    M["RBehTimMultiCondPct"] = fpct(tb.get("cycles_more_than_one_condition"), tb.get("cycles"), 2)
    M["RBehTimStricterPct"] = fpct(tb.get("cycles_composed_limits_stricter_than_mode"), tb.get("cycles"), 2)
    for camp, P in (("timing_behaviour", "RBehTim"), ("compare_behaviour", "RBehCmp"), ("injection_behaviour", "RBehInj")):
        b = (extra or {}).get(camp) or {}
        mf = b.get("mode_fraction") or {}
        M[P + "Nominal"] = f(mf.get("nominal"), 2, 100)
        stopped = sum(mf.get(k, 0) for k in ("protective_stop", "protective_stop_latched", "emergency_stop")) if mf else None
        degraded = sum(mf.get(k, 0) for k in ("low_confidence", "degraded_stream", "geometric_fallback", "overrun_shed")) if mf else None
        M[P + "Stopped"] = f(stopped, 2, 100)
        M[P + "Degraded"] = f(degraded, 2, 100)
        ps = (b.get("by_strategy") or {}).get("proposed") or {}
        M[P + "QpRelaxed"] = fi(ps.get("qp_relaxed"))
        M[P + "LearnedPct"] = fpct(ps.get("learned_rows"), ps.get("cycles"), 1)
    # crossings table
    rows = []
    for exp, label, _ in CAMPAIGNS:
        p = prop(exp)
        for basis, bl in (("below_floor_estimated", "estimated"), ("below_floor_true", "true")):
            s = p.get(basis) or {}
            if not s:
                rows.append(row(label, bl, *([MISSING] * 8)))
                continue
            st = s.get("state_at_onset") or {}
            mt = s.get("min_true_sep_m")
            rows.append(row(label, bl, fi(s["episodes"]), fi(s["cycles"]), fi(s["with_lunge_within_2s"]),
                            fi(s["in_nominal_mode"]), fi(st.get("standstill", 0)), fi(st.get("decelerating", 0)),
                            fi(st.get("moving", 0)), f(mt, 0, 1000) if mt is not None else "--"))
    T["tab_crossings"] = rows


def calibration(res, M):
    c = res.get("calibration_rule_applied") or {}
    p = c.get("pooled") or {}
    M["RCalMatched"] = fi(p.get("matched_cycles"))
    M["RCalPFiftyMm"] = f(p.get("p50"), 0, 1000)
    M["RCalPNineFiveMm"] = f(p.get("p95"), 0, 1000)
    M["RCalPNineNineMm"] = f(p.get("p99"), 0, 1000)
    M["RCalMaxMm"] = f(p.get("max"), 0, 1000)
    M["RCalMarginM"] = f(c.get("position_margin_m"), 2)
    M["RCalZdM"] = f(c.get("Z_d_m"), 2)


def stop_check(summary_path, csv_path, M):
    keys = ("RStopSamples", "RStopPathExceed", "RStopPathRatio", "RStopDispExceed", "RStopDispRatio", "RStopTimeExceed",
            "RStopTimeRatio", "RStopVrMax")
    for k in keys:
        M[k] = MISSING
    if summary_path and Path(summary_path).exists():
        s = Path(summary_path).read_text()
        m = re.search(r"samples=(\d+)", s)
        if m:
            M["RStopSamples"] = fi(int(m.group(1)))
        for lab, n in (("path length", "Path"), ("displacement", "Disp"), ("braking time", "Time")):
            m = re.search(lab + r"[^:]*:\s*(\d+)\s*\(worst ratio\s*([0-9.]+)\)", s)
            if m:
                M[f"RStop{n}Exceed"] = fi(int(m.group(1)))
                M[f"RStop{n}Ratio"] = f(float(m.group(2)), 3)
    if csv_path and Path(csv_path).exists():
        vr = [float(r["v_r"]) for r in csv.DictReader(open(csv_path))]
        if vr:
            M["RStopVrMax"] = f(max(vr), 2)


# ------------------------------------------------------------------------------- retained (release 3.0), protocol, extra
def protocol(res, M, T):
    p = res.get("protocol") or {}
    run = p[sorted(p)[0]] if p else {}
    rows = []
    for k, label in (("modbus", "Modbus TCP (FC01, FC03, FC06)"), ("rest", "REST (GET /api/v1/status)")):
        c = run.get(k, {})
        rows.append(row(label, fi(c.get("n")), f(c.get("median_ms"), 3), f(c.get("p95_ms"), 3), f(c.get("p99_ms"), 3),
                        fi(c.get("failed"))))
    T["tab_protocol"] = rows


def conformance(res30, M, T):
    c = res30.get("conformance") or {}
    run = c[sorted(c)[0]] if c else {}
    M["RConfPass"] = fi(run.get("pass"))
    M["RConfFail"] = fi(run.get("fail"))
    items = run.get("items") or []
    M["RConfItems"] = fi(len(items)) if items else MISSING
    M["RConfInfo"] = fi(sum(1 for i in items if i["result"] == "info")) if items else MISSING
    M["RConfVersion"] = run.get("controller_version") or MISSING
    for k in ("RConfURSixObserved", "RConfURElevenMs", "RConfURTenMs"):
        M[k] = MISSING
    rows = []
    esc = lambda s: (s.replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
                     .replace("#", r"\#").replace("+/-", r"$\pm$").replace("^2", r"$^2$").replace(">=", r"$\geq$"))
    brk = lambda s: s.replace(",", r",\allowbreak{}").replace(r"\_", r"\_\allowbreak{}")
    for i in sorted(items, key=lambda i: int(i["item_id"].split("-")[1])):
        rows.append(row(i["item_id"], brk(esc(i["document_clause"])), brk(esc(i["expected"])), brk(esc(i["observed"])),
                        esc(i["result"])))
        if i["item_id"] == "UR-06":
            m6 = re.search(r"([0-9]+(?:\.[0-9]+)?)", i["observed"])
            M["RConfURSixObserved"] = m6.group(1) if m6 else MISSING
        for iid, key in (("UR-11", "RConfURElevenMs"), ("UR-10", "RConfURTenMs")):
            if i["item_id"] == iid:
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ms", i["observed"])
                M[key] = m.group(1) if m else MISSING
    T["tab_conformance"] = rows or [row(MISSING, MISSING, MISSING, MISSING, MISSING)]


def cbf(res30, M):
    c = res30.get("cbf_training") or {}
    m = c[sorted(c)[0]] if c else {}
    M["RCbfNTrain"] = fi(m.get("n_train"))
    M["RCbfNVal"] = fi(m.get("n_val"))
    M["RCbfNTest"] = fi(m.get("n_test"))
    M["RCbfNGray"] = fi(m.get("n_gray"))
    M["RCbfEpochs"] = fi(m.get("epochs_run"))
    M["RCbfMAEmm"] = f(m.get("test_mae_m"), 0, 1000)
    M["RCbfUnsafe"] = fi(m.get("test_unsafe"))
    M["RCbfFalseSafe"] = f(m.get("false_safe_rate_given_unsafe"), 1, 100)
    fs = m.get("false_safe_wilson95") or [None, None]
    M["RCbfFalseSafeCI"] = fci(fs[0], fs[1], 1, 100)
    M["RCbfFalseUnsafe"] = f(m.get("false_unsafe_rate_given_safe"), 1, 100)
    M["RCbfAbstTest"] = f(m.get("abstention_rate_test"), 1, 100)
    M["RCbfAbstGray"] = f(m.get("abstention_rate_gray"), 1, 100)
    M["RCbfLipCert"] = f(m.get("lipschitz_certified_upper_bound"), 1)
    M["RCbfLipSearch"] = f(m.get("lipschitz_search_lower_bound"), 2)


def extra_sections(extra, M):
    ex = extra or {}
    cm = ex.get("code_metrics") or {}
    M["RCodeShared"] = fi(cm.get("shared_loc"))
    for k, n in (("ur_rtde", "UR"), ("kuka_fri", "KUKA"), ("abb_egm", "ABB")):
        M[f"RCode{n}"] = fi((cm.get("adapter_loc") or {}).get(k))
    M["RCodeFunctions"] = fi(cm.get("functions"))
    M["RCodeCCNMean"] = f(cm.get("ccn_mean"), 1)
    M["RCodeCCNMax"] = fi(cm.get("ccn_max"))
    M["RCodeCCNOverTen"] = fi(cm.get("ccn_over_10"))
    ib = ex.get("injection_breakdown") or {}
    comm = ib.get("comm_by_param") or {}
    sm = lambda keys, fld: sum(v[fld] for k, v in comm.items() if k in keys)
    M["RCommShortInj"] = fi(sm(("1", "2"), "injected")) if comm else MISSING
    M["RCommShortDet"] = fi(sm(("1", "2"), "detected")) if comm else MISSING
    M["RCommLongInj"] = fi(sm(("3", "4", "5"), "injected")) if comm else MISSING
    M["RCommLongDet"] = fi(sm(("3", "4", "5"), "detected")) if comm else MISSING
    lu = ib.get("lunge") or {}
    M["RLungeInj"] = fi(lu.get("injected"))
    M["RLungeCrossed"] = fi(lu.get("floor_crossed_latched"))
    M["RLungeHeld"] = fi(lu.get("floor_held"))
    M["RLungeWhileStopped"] = fi(lu.get("while_stopped"))
    ld = ex.get("logger_drops") or {}
    M["RLogCyclesDropped"] = fi(ld.get("cycles_dropped")) if ld else MISSING
    M["RLogEventsDropped"] = fi(ld.get("events_dropped")) if ld else MISSING
    M["RLogRuns"] = fi(ld.get("runs")) if ld else MISSING


def load(path, prov, label):
    if path and Path(path).exists():
        prov.append(f"{label} sha256 {hashlib.sha256(Path(path).read_bytes()).hexdigest()}  ({path})")
        return json.loads(Path(path).read_text())
    prov.append(f"{label} ABSENT ({path or 'not given'}): its numbers print as ??")
    return {}



def binom_upper(x, n, alpha=0.05):
    """Exact one-sided (1-alpha) upper bound on a binomial proportion (Clopper-Pearson); x=0 gives 1-alpha^(1/n)."""
    if not ok(x) or not ok(n) or n <= 0:
        return None
    x, n = int(x), int(n)
    if x >= n:
        return 1.0
    def cdf(p):  # P(X <= x | n, p)
        tot, term = 0.0, (1 - p) ** n
        for k in range(0, x + 1):
            if k > 0:
                term *= (n - k + 1) / k * p / (1 - p)
            tot += term
        return tot
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def r4_additions(res, extra, M, a):
    """Macros added for the final text of R4 (2026-11-21). Supplementary where stated in the text."""
    t = res.get("timing") or {}
    nb, xb = get(t, "blocks.n"), get(t, "blocks.with_retained_miss")
    ub = get(t, "blocks.upper95_p_block_has_miss")
    if ub is None:
        ub = binom_upper(xb, nb)
    M["RTimBlockBound"] = fsig(ub, 2)
    M["RTimBlockBoundPct"] = f(ub, 1, 100)
    # retained misses in detail (scripts/timing_miss_detail.py, supplementary)
    md = load(a.miss_detail, a._prov, "timing_miss_detail.json (supplementary)") if a.miss_detail else {}
    bl = (md or {}).get("blocks_with_retained_miss") or []
    if bl:
        b = bl[0]
        M["RTimMissBlock"] = b["run"].rsplit("_", 1)[-1]
        M["RTimMissBlockN"] = fi(b["misses"])
        M["RTimMissWakeMinMs"] = f(min(b["wake_delay_ms"]), 0)
        M["RTimMissWakeMaxMs"] = f(max(b["wake_delay_ms"]), 0)
        M["RTimMissExecMaxUs"] = fsig(max(b["exec_from_wake_ms"]), 2, 1000)
        M["RTimMissSpanS"] = f(max(b["t_since_block_start_s"]) / 60.0, 0)
        M["RTimMissAgeMaxMs"] = f(b["max_estimate_age_ms"], 0)
    else:
        for k in ("RTimMissBlock", "RTimMissBlockN", "RTimMissWakeMinMs", "RTimMissWakeMaxMs", "RTimMissExecMaxUs",
                  "RTimMissSpanS", "RTimMissAgeMaxMs"):
            M[k] = MISSING
    un = (md or {}).get("unclosed_runs") or {}
    M["RTimInterrupted"] = fi(len(un.get("timing_campaign", []))) if md else MISSING
    M["RFiInterrupted"] = fi(len(un.get("fault_injection", []))) if md else MISSING
    # stops of the QP chain and estimated floor crossings by strategy, comparison campaign
    B = (res.get("behaviour") or {}).get("baseline_compare") or {}
    names = {"proposed": "Prop", "hc_cbf": "HCCBF", "ssm": "SSM", "pf": "PF", "pf_ssm": "PFSSM"}
    for s, P in names.items():
        v = B.get(s) or {}
        n = v.get("cycles")
        cs = v.get("controller_stops") or {}
        M[f"RCmpDisp{P}"] = fpct(v.get("dispatched_cycles"), n, 1)
        M[f"RCmpQpFail{P}"] = fpct(cs.get("qp_failed", 0) if v else None, n, 1)
        M[f"RCmpConflict{P}"] = fpct(cs.get("limit_conflict", 0) if v else None, n, 1)
        M[f"RCmpEstBelow{P}"] = fi(get(v, "below_floor_estimated.episodes"))
        M[f"RCmpTrueBelow{P}"] = fi(get(v, "below_floor_true.episodes"))
    # crossings and estimate error per campaign, proposed controller
    Bh = res.get("behaviour") or {}
    for exp, P in (("timing_campaign", "Tim"), ("baseline_compare", "Cmp"), ("fault_injection", "Inj"),
                   ("fault_sensitivity", "Sens")):
        v = (Bh.get(exp) or {}).get("proposed") or {}
        M[f"RX{P}ErrAboveMarginPct"] = f(v.get("share_closest_error_above_margin"), 2, 100)
        M[f"RX{P}GtBelowEstAbove"] = fi(v.get("true_below_floor_while_estimate_above_cycles"))
        for basis, Q in (("below_floor_estimated", "Est"), ("below_floor_true", "True")):
            s = v.get(basis) or {}
            st = s.get("state_at_onset") or {}
            M[f"RX{P}{Q}Episodes"] = fi(s.get("episodes"))
            M[f"RX{P}{Q}Standstill"] = fi(st.get("standstill", 0) if s else None)
            M[f"RX{P}{Q}Lunge"] = fi(s.get("with_lunge_within_2s"))
            M[f"RX{P}{Q}Nominal"] = fi(s.get("in_nominal_mode"))
            mt = s.get("min_true_sep_m")
            M[f"RX{P}{Q}MinTrueMm"] = f(mt, 0, 1000) if mt is not None else "--"
    # stopping check: the samples whose braking time exceeded T_s (tools/stop_check output)
    if a.stop_csv and Path(a.stop_csv).exists():
        rows = list(csv.DictReader(open(a.stop_csv)))
        ex = [r for r in rows if float(r["T_eq3"]) > 0 and float(r["t_stop"]) > float(r["T_eq3"])]
        M["RStopTimeExceedVrMaxMm"] = f(max(float(r["v_r"]) for r in ex) * 1000, 1) if ex else "--"
        M["RStopTimeExceedDiffMs"] = f(max((float(r["t_stop"]) - float(r["T_eq3"])) * 1000 for r in ex), 1) if ex else "--"
        pr = sorted(float(r["path_max"]) / float(r["S_eq3"]) for r in rows if float(r["S_eq3"]) > 0)
        M["RStopPathRatioMed"] = f(pr[len(pr) // 2], 2) if pr else MISSING
    else:
        for k in ("RStopTimeExceedVrMaxMm", "RStopTimeExceedDiffMs", "RStopPathRatioMed"):
            M[k] = MISSING
    # conformance repeated with release 3.1 (additional run outside the pre-registration)
    cdir = Path(a.conformance_r31) if a.conformance_r31 else None
    runs31 = sorted(cdir.glob("*_conformance_ur_rtde")) if cdir and cdir.exists() else []
    if runs31:
        d = runs31[-1]
        items = list(csv.DictReader(open(d / "conformance.csv")))
        man = json.loads((d / "manifest.json").read_text())
        M["RConfRThreeOnePass"] = fi(sum(i["result"] == "pass" for i in items))
        M["RConfRThreeOneFail"] = fi(sum(i["result"] == "fail" for i in items))
        M["RConfRThreeOneInfo"] = fi(sum(i["result"] == "info" for i in items))
        M["RConfRThreeOneVersion"] = man.get("controller_version") or MISSING
        M["RConfRThreeOneDate"] = (lambda v: f"{int(v[8:10])} {['January','February','March','April','May','June','July','August','September','October','November','December'][int(v[5:7])-1]} {v[:4]}" if len(v) >= 10 else MISSING)(man.get("end_utc", ""))
        for iid, key in (("UR-06", "RConfRThreeOneURSix"), ("UR-11", "RConfRThreeOneURElevenMs"),
                         ("UR-10", "RConfRThreeOneURTenMs")):
            it = [i for i in items if i["item_id"] == iid]
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", it[0]["observed"]) if it else None
            M[key] = m.group(1) if m else MISSING
        same = [i["item_id"] for i in items]
        M["RConfRThreeOneItems"] = fi(len(same))
        prov_c = hashlib.sha256((d / "MANIFEST.sha256").read_bytes()).hexdigest()
        M["RConfRThreeOneManifest"] = prov_c[:12]
        a._prov.append(f"conformance run (release 3.1) {d.name} MANIFEST sha256 {prov_c}")
    else:
        for k in ("RConfRThreeOnePass", "RConfRThreeOneFail", "RConfRThreeOneInfo", "RConfRThreeOneVersion",
                  "RConfRThreeOneDate", "RConfRThreeOneURSix", "RConfRThreeOneURElevenMs", "RConfRThreeOneURTenMs",
                  "RConfRThreeOneItems", "RConfRThreeOneManifest"):
            M[k] = MISSING

    # ---- review of 21.11.2026: further macros (supplementary where stated in the text)
    tcy = t.get("cycles") or {}
    M["RTimSkippedRel"] = fi(tcy.get("skipped_releases_from_t_release"))
    blocks = get(extra, "timing_behaviour.blocks", []) or []
    if blocks:
        per = 100 * 60 * 50  # cycles of a 100-min block at 50 Hz
        worst = max(blocks, key=lambda b: per - b["cycles"])
        M["RTimSkippedBlockMax"] = fi(per - worst["cycles"])
        M["RTimSkippedBlockName"] = worst["variant"].rsplit("_", 1)[-1]
        r = sorted(b["exec_max_ms"] / b["exec_p99_ms"] for b in blocks)
        n = len(r)
        med = r[n // 2] if n % 2 else 0.5 * (r[n // 2 - 1] + r[n // 2])
        M["RBlkMaxToPNineNine"] = f(med, 1)
    else:
        for k in ("RTimSkippedBlockMax", "RTimSkippedBlockName"):
            M[k] = MISSING
    un = (md or {}).get("unclosed_runs") or {}
    nint = len(un.get("timing_campaign", []))
    M["RTimBlockBoundWorst"] = fsig(binom_upper((xb or 0) + nint, (nb or 0) + nint), 2) if md and nb else MISSING
    M["RTimBlocksPlusInterrupted"] = fi((nb or 0) + nint) if md and nb else MISSING
    # stops of the QP chain, timing campaign (proposed controller)
    tim = ((res.get("behaviour") or {}).get("timing_campaign") or {}).get("proposed") or {}
    cs = tim.get("controller_stops") or {}
    if cs:
        tot = cs.get("qp_failed", 0) + cs.get("limit_conflict", 0)
        M["RBehTimQpStopsTotal"] = fi(tot)
        M["RBehTimQpStopsPct"] = fpct(tot, tim.get("cycles"), 1)
    else:
        M["RBehTimQpStopsTotal"] = M["RBehTimQpStopsPct"] = MISSING
    # geometric fallback (raised after every relaxation of the QP; only the proposed controller has a learned row)
    tb = (extra or {}).get("timing_behaviour") or {}
    mf = tb.get("mode_fraction") or {}
    M["RBehTimFallback"] = f(mf.get("geometric_fallback"), 2, 100)
    M["RBehTimDegradedStream"] = f(mf.get("degraded_stream"), 2, 100)
    cbx = (extra or {}).get("compare_behaviour") or {}
    cmf = cbx.get("mode_fraction") or {}
    pcy = ((cbx.get("by_strategy") or {}).get("proposed") or {}).get("cycles")
    if cmf and pcy and cbx.get("cycles"):
        M["RCmpFallbackPropPct"] = f(cmf.get("geometric_fallback", 0) * cbx["cycles"] / pcy, 0, 100)
    else:
        M["RCmpFallbackPropPct"] = MISSING
    # estimated-floor episodes against the raised floor (0.30 m) of geometric fallback
    for exp, P in (("timing_campaign", "Tim"), ("baseline_compare", "Cmp"), ("fault_injection", "Inj")):
        L = get((res.get("behaviour") or {}).get(exp) or {}, "proposed.below_floor_estimated.list", []) or []
        M[f"RX{P}EstRaisedFloor"] = fi(sum(1 for x in L if x.get("floor_m", 0) > 0.29)) if L else "0"
    # timing campaign: injected faults and constraint-violation episodes
    fit = res.get("faults_in_timing_campaign") or {}
    pc = fit.get("per_category") or {}
    M["RFtCvInjected"] = fi((pc.get("constraint_violation") or {}).get("injected"))
    M["RFtCvEpisodes"] = fi(get(fit, "reliability.per_category.constraint_violation.events"))
    # SSM baseline: intrusion distance selected by the tuning rule
    ts = res.get("tuning_selection") or {}
    M["RTuneSSMCmm"] = f((ts.get("ssm") or {}).get("value"), 0, 1000) if (ts.get("ssm") or {}).get("parameter") == "ssm.C" else MISSING
    # no memory-allocation fault is injected in the timing campaign (rate 0): not a missing value
    for k in ("RFtDetMaxMem", "RFtDetMedMem"):
        if M.m.get(k) == MISSING:
            M[k] = "--"

def supp_additions(a, M, T):
    """Supplementary analyses of the final R4 text (scripts/supp_r4.py -> results_supp.json). Not pre-registered."""
    S = load(a.supp, a._prov, "results_supp.json (supplementary)") if a.supp else {}
    S = S or {}
    keys = []
    def put(k, v):
        keys.append(k); M[k] = v
    u = S.get("U1_timing") or {}
    d = u.get("duration_s") or {}
    put("RSuStopEpN", fi(u.get("episodes")))
    put("RSuStopEpPerH", fi(round(u["episodes_per_h"], -2)) if u.get("episodes_per_h") else MISSING)
    put("RSuStopEpMedMs", f(d.get("p50"), 0, 1000) if d else MISSING)
    put("RSuStopEpPNineFiveMs", f(d.get("p95"), 0, 1000) if d else MISSING)
    put("RSuStopEpMaxS", f(d.get("max"), 1) if d else MISSING)
    put("RSuStopEpOneCyclePct", f(u.get("share_episodes_le_1_cycle"), 0, 100))
    put("RSuStopSepEstMed", f(get(u, "sep_est_in_stop.p50"), 2))
    put("RSuStopSepEstPFive", f(get(u, "sep_est_in_stop.p5"), 2))
    put("RSuStopSepTrueMed", f(get(u, "sep_true_in_stop.p50"), 2))
    put("RSuStopHMedMm", f(get(u, "h_geo_in_stop.p50"), 0, 1000))
    c = S.get("U1_compare") or {}
    for k, n in (("proposed", "Prop"), ("hc_cbf", "HCCBF"), ("ssm", "SSM"), ("pf", "PF"), ("pf_ssm", "PFSSM")):
        x = c.get(k) or {}
        put(f"RSuStill{n}", f(x.get("standstill_share"), 0, 100) if k != "pf" else f(x.get("standstill_share"), 2, 100))
        put(f"RSuStopEpPerH{n}", fi(round(x["episodes_per_h"], -2)) if x.get("episodes_per_h") else "0")
    s4 = S.get("U4_logged_stops") or {}
    put("RSuLogStopN", fi(s4.get("n")))
    put("RSuLogStopVrMedMms", f(get(s4, "v_r.p50"), 0, 1000))
    put("RSuLogStopVrMaxMms", f(get(s4, "v_r.max"), 0, 1000))
    put("RSuLogStopPathExceed", fi(s4.get("path_exceeds_Seq3")))
    put("RSuLogStopPathRatioMax", f(get(s4, "path_over_Seq3.max"), 2))
    put("RSuLogStopTimeExceed", fi(s4.get("braking_exceeds_Teq3")))
    w = S.get("U6_watchdog_stops") or {}
    put("RSuWatchdogStops", fi(w.get("total")))
    put("RSuWatchdogBlocks", fi(w.get("blocks_with")))
    cv = S.get("U2_constraint_violation_split") or {}
    put("RSuCvGenerated", fi(cv.get("generated")))
    put("RSuCvInjected", fi(cv.get("after_injected_lunge")))
    put("RSuCvStoppedGenH", f(cv["stopped_s_generated"] / 3600.0, 1) if cv.get("stopped_s_generated") is not None else MISSING)
    put("RSuCvStoppedGenPct", f(cv.get("share_of_time_stopped_by_generated"), 1, 100))
    ab = get(S, "U3_ablation_by_load.paired") or {}
    def pr(k, fld, nd, sc=1.0):
        x = ab.get(k) or {}
        v = x.get(fld)
        return f(v, nd, sc) if v is not None else MISSING
    def prci(k, fld, nd, sc=1.0):
        x = (ab.get(k) or {}).get(fld)
        return fci(x[0], x[1], nd, sc) if x else MISSING
    put("RSuAblAOneIdleUs", pr("A1-A3|idle", "median_diff_of_medians_us", 0))
    put("RSuAblAOneIdleCI", prci("A1-A3|idle", "ci95_us", 0))
    put("RSuAblAOneLoadUs", pr("A1-A3|load", "median_diff_of_medians_us", 0))
    put("RSuAblAOneLoadCI", prci("A1-A3|load", "ci95_us", 0))
    put("RSuAblAThreeAZeroIdleCI", prci("A3-A0|idle", "ci95_us", 0))
    put("RSuAblAThreeAZeroLoadCI", prci("A3-A0|load", "ci95_us", 1))
    put("RSuAblATwoLoadMaxMs", pr("A2-A3|load", "median_diff_of_max_ms", 1))
    put("RSuAblATwoaIdleUs", pr("A2a-A3|idle", "median_diff_of_medians_us", 0))
    put("RSuAblATwoaIdleCI", prci("A2a-A3|idle", "ci95_us", 0))
    put("RSuAblATwobIdleUs", pr("A2b-A3|idle", "median_diff_of_medians_us", 0))
    put("RSuAblATwobIdleCI", prci("A2b-A3|idle", "ci95_us", 0))
    put("RSuAblATwoLoadMaxCI", prci("A2-A3|load", "ci95_max_ms", 2))
    bl = get(S, "U3_ablation_by_load.by_configuration_and_load") or {}
    put("RSuAblATwoLoadSDRelMs", f((bl.get("A2|load") or {}).get("median_sd_release_ms"), 1))
    u5 = (S.get("U5_sensitivity_episodes") or {}).get("clustered_x1.5") or {}
    put("RSuClusTrackEp", fi((u5.get("episodes_by_category") or {}).get("tracking_loss")))
    put("RSuClusTrackInj", fi((u5.get("injected_by_category") or {}).get("tracking_loss")))
    # run-bootstrap intervals per category for the reliability table
    rb = S.get("U2_rates_by_category") or {}
    rows = T.get("tab_reliability") or []
    new = []
    for (k, label), r in zip(CATS, rows):
        x = rb.get(k)
        if k == "configuration_inconsistency":
            cell = "n/a"
        elif x and x.get("run_bootstrap_ci95") and x.get("episodes"):
            cell = fci(x["run_bootstrap_ci95"][0], x["run_bootstrap_ci95"][1], 3)
        elif S:
            cell = "--"
        else:
            cell = MISSING
        r = r.rstrip()
        assert r.endswith("\\\\"), r
        new.append(r[:-2].rstrip() + " & " + cell + " \\\\")
    if rows:
        T["tab_reliability"] = new
    print("supp macros:", len(keys), "missing:", [k for k in keys if M.m.get(k) == MISSING])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--extra", default="")
    ap.add_argument("--results-r30", default="")
    ap.add_argument("--stop-summary", default="")
    ap.add_argument("--stop-csv", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--conformance-r31", default="")
    ap.add_argument("--miss-detail", default="")
    ap.add_argument("--supp", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    prov = []
    res = load(a.results, prov, "results.json (v4)")
    extra = load(a.extra, prov, "results_extra.json (v4)")
    res30 = load(a.results_r30, prov, "results.json (release 3.0, retained items only)")
    for p, lab in ((a.stop_summary, "stop_check_summary.txt"), (a.stop_csv, "stop_check_compare.csv")):
        if p and Path(p).exists():
            prov.append(f"{lab} sha256 {hashlib.sha256(Path(p).read_bytes()).hexdigest()}  ({p})")
        else:
            prov.append(f"{lab} ABSENT")
    M, T = Macros(), {}
    timing(res, extra, M, T)
    ablation(res, extra, M, T)
    faults_section(res, "Fi", "fault_injection", M, T, table_name="tab_faults")
    faults_section(res, "Ft", "faults_in_timing_campaign", M, T, rel_table="tab_reliability")
    sensitivity_table(extra, M, T)
    tuning_compare(res, M, T)
    behaviour(res, extra, M, T)
    calibration(res, M)
    stop_check(a.stop_summary, a.stop_csv, M)
    protocol(res, M, T)
    conformance(res30, M, T)
    cbf(res30, M)
    extra_sections(extra, M)
    a._prov = prov
    r4_additions(res, extra, M, a)
    supp_additions(a, M, T)
    # names used in the availability table
    for src, dst in (("Fi", "Fi"), ("Ft", "Tim")):
        for k in ("Outside", "Permitted", "Diff", "Scale"):
            M[f"RAv{dst}{k}"] = M.m.get(f"R{src}Av{k}", MISSING)
    M["RAvTimUnrecS"] = M.m.get("RFtAvUnrecS", MISSING)
    header = "% generated by scripts/make_numbers.py -- do not edit\n% " + "\n% ".join(prov)
    (out / "r4_numbers.tex").write_text(M.tex(header))
    for name, rows in T.items():
        (out / f"{name}.tex").write_text(header + "\n" + "\n".join(typeset_minus(r) for r in rows) + "\n")
    (out / "provenance.txt").write_text("\n".join(prov) + "\n")
    n_missing = sum(1 for v in M.m.values() if v == MISSING)
    print(f"{len(M.m)} macros ({n_missing} missing), {len(T)} tables -> {out}")


if __name__ == "__main__":
    main()
