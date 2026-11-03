#!/usr/bin/env python3
"""Generate every number and every data table of manuscript R3 from results files.

    python3 make_numbers.py --results results.json [--extra results_extra.json] --out ../numbers

Inputs
  results.json        written by analysis/report.py (pre-registered pipeline, queue3 step 6)
  results_extra.json  written by scripts/extra_analysis.py (supplementary analyses)
Outputs (in --out)
  r3_numbers.tex      one \\newcommand per number used in the text (semantic names, prefix R)
  tab_*.tex           table bodies (rows only); the table frames live in the manuscript
  provenance.txt      SHA-256 of the inputs

Nothing here contains a number: a quantity that is absent from the inputs is printed as a red
"??" (\\missingnum), so a missing result cannot go unnoticed in the compiled PDF.
"""
import argparse
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
STRAT = {"proposed": "Proposed (geometric + learned CBF-QP)", "hc_cbf": "HC-CBF (geometric CBF-QP)",
         "ssm": "SSM (ISO/TS 15066 speed scaling)", "pf": "PF (potential field)"}
STRAT_SHORT = {"proposed": "Proposed", "hc_cbf": "HC-CBF", "ssm": "SSM", "pf": "PF"}
PARAM_TEX = {"control.kappa": r"$\kappa$ (s$^{-1}$)", "ssm.C": r"$C$ (m)", "pf.k_rep": r"$k_{\mathrm{rep}}$"}


# ------------------------------------------------------------------------------- helpers
def get(d, path, default=None):
    """Dotted path; '*' selects the only (or first, sorted) key of a run-keyed dict."""
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
    return v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def f(v, nd=2, scale=1.0):
    if not ok(v):
        return MISSING
    x = float(v) * scale
    s = f"{x:,.{nd}f}".replace(",", "{,}")
    return s


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
    return rf"{m}\times10^{{{int(e)}}}"


def fp(v):
    if not ok(v):
        return MISSING
    v = float(v)
    if v < 0.001:
        return r"$<$0.001"
    return f"{v:.3f}"


def fci(lo, hi, nd=2, scale=1.0):
    if not (ok(lo) and ok(hi)):
        return MISSING
    return f"[{f(lo, nd, scale)}, {f(hi, nd, scale)}]"


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


_NEG = re.compile(r"(?<![A-Za-z0-9\-])-(?=\d)")


def typeset_minus(v):
    """Print a negative number with a true minus sign (text or math mode), not a hyphen."""
    return _NEG.sub(r"\\ensuremath{-}", v) if isinstance(v, str) else v


def row(*cells):
    return " & ".join(cells) + r" \\"


# ------------------------------------------------------------------------------- sections
def timing(res, M, T):
    t = res.get("timing") or {}
    M["RTimRuns"] = fi(get(t, "runs"))
    M["RTimCyclesTotal"] = fi(get(t, "cycles.total"))
    M["RTimCyclesTotalSci"] = fsig(get(t, "cycles.total"), 3)
    M["RTimCyclesInj"] = fi(get(t, "cycles.with_injected_overrun_excluded"))
    M["RTimCyclesRet"] = fi(get(t, "cycles.retained"))
    M["RTimMissRet"] = fi(get(t, "cycles.deadline_misses_retained"))
    M["RTimMissInj"] = fi(get(t, "cycles.deadline_misses_in_injected"))
    M["RTimLateRel"] = fi(get(t, "cycles.late_releases"))
    for k, n in (("median", "Med"), ("p95", "PNineFive"), ("p99", "PNineNine"), ("max", "Max"), ("sd", "SD")):
        M[f"RTimExec{n}"] = fsig(get(t, f"exec_ms.{k}"), 3)
        M[f"RTimExec{n}Us"] = fsig(get(t, f"exec_ms.{k}"), 3, 1000)
    M["RTimExecMaxPct"] = f(get(t, "exec_ms.max"), 1, 100 / 20.0)  # % of the 20 ms period
    M["RTimExecMedPct"] = f(get(t, "exec_ms.median"), 2, 100 / 20.0)
    M["RTimRelMean"] = f(get(t, "release_interval_ms.mean"), 3)
    M["RTimRelSD"] = fsig(get(t, "release_interval_ms.sd"), 2)
    M["RTimRelSDUs"] = fsig(get(t, "release_interval_ms.sd"), 2, 1000)
    names = [("state", "State read (robot + human)"), ("nominal", "Nominal controller"), ("geo", "Geometric barrier rows"),
             ("learned", "Learned barrier (forward + gradient)"), ("qp", "QP filter + SSM scaling"),
             ("dispatch", "Command dispatch"), ("log", "Bookkeeping and record")]
    rows = []
    for k, label in names:
        v = get(t, f"stage_median_ms.{k}")
        M["RTimStage" + k.capitalize() + "Us"] = fsig(v, 3, 1000)
        rows.append(row(label, fsig(v, 3, 1000)))
    T["tab_stages"] = rows
    M["RTimAgeMed"] = f(get(t, "estimate_age_ms.median"), 1)
    M["RTimAgePNineFive"] = f(get(t, "estimate_age_ms.p95"), 1)
    M["RTimAgeMax"] = f(get(t, "estimate_age_ms.max"), 1)
    am = get(t, "estimate_age_ms.median")
    M["RSageMedMm"] = f(am * (1.6 + 0.3), 0) if ok(am) else MISSING  # (v_h + v_r) t_age at v_r = 0.3 m/s, in mm
    M["RTimBlocks"] = fi(get(t, "blocks.n"))
    M["RTimBlocksMiss"] = fi(get(t, "blocks.with_retained_miss"))
    ub = get(t, "blocks.upper95_p_block_has_miss")
    M["RTimBlockBound"] = fsig(ub, 2)
    M["RTimBlockBoundPct"] = f(ub, 1, 100)
    M["RTimRuleThree"] = fsig(get(t, "blocks.rule_of_three"), 2)
    M["RTimExclNonRT"] = fi(len(get(t, "excluded_non_rt", [])) if t else None)


def ablation(res, extra, M, T):
    a = get(res, "ablation.configurations", {}) or {}
    rows = []
    for k, label in ABL:
        c = a.get(k, {})
        ci = c.get("median_ci95_over_run_medians", [None, None]) if c else [None, None]
        nd = 3
        rows.append(row(label, fi(c.get("runs")), fi(c.get("cycles")), f(c.get("median_ms"), nd),
                        fci(ci[0], ci[1], nd), f(c.get("p95_ms"), nd), f(c.get("p99_ms"), nd), f(c.get("max_ms"), 2),
                        f(c.get("sd_exec_ms"), nd), f(c.get("sd_release_interval_ms"), nd), f(c.get("miss_pct"), 3)))
        key = k.replace("2a", "Twoa").replace("2b", "Twob").replace("2c", "Twoc").replace("0", "Zero").replace("1", "One") \
               .replace("2", "Two").replace("3", "Three")
        M[f"RAbl{key}Med"] = f(c.get("median_ms"), 3)
        M[f"RAbl{key}MedUs"] = fsig(c.get("median_ms"), 3, 1000)
        M[f"RAbl{key}Max"] = f(c.get("max_ms"), 2)
        M[f"RAbl{key}PNineNine"] = f(c.get("p99_ms"), 3)
        M[f"RAbl{key}Miss"] = f(c.get("miss_pct"), 3)
        M[f"RAbl{key}SDRel"] = f(c.get("sd_release_interval_ms"), 3)
    T["tab_ablation"] = rows
    tot = sum((a.get(k, {}) or {}).get("cycles", 0) or 0 for k, _ in ABL) if a else None
    M["RAblCyclesTotal"] = fi(tot) if tot else MISSING
    M["RAblRuns"] = fi(sum((a.get(k, {}) or {}).get("runs", 0) or 0 for k, _ in ABL)) if a else MISSING
    notes = get(res, "ablation.notes", [])
    M["RAblExcluded"] = fi(len(notes)) if a else MISSING
    if a and "A0" in a and "A3" in a:
        M["RAblAThreeMinusAZeroUs"] = fsig((a["A3"]["median_ms"] - a["A0"]["median_ms"]), 2, 1000)
        M["RAblAOneMinusAThreeUs"] = fsig((a["A1"]["median_ms"] - a["A3"]["median_ms"]), 3, 1000) if "A1" in a else MISSING
    else:
        M["RAblAThreeMinusAZeroUs"] = MISSING
        M["RAblAOneMinusAThreeUs"] = MISSING


def faults_section(res, prefix, key, M, T, table_name=None, rel_table=None):
    fr = res.get(key) or {}
    M[f"R{prefix}Runs"] = fi(get(fr, "runs"))
    pc = get(fr, "per_category", {}) or {}
    inj = sum(v.get("injected", 0) for v in pc.values()) if pc else None
    det = sum(v.get("detected", 0) for v in pc.values()) if pc else None
    und_stop = sum(v.get("undetected_while_stopped", 0) for v in pc.values()) if pc else None
    und_oth = sum(v.get("undetected_other", 0) for v in pc.values()) if pc else None
    M[f"R{prefix}Injected"] = fi(inj)
    M[f"R{prefix}Detected"] = fi(det)
    M[f"R{prefix}UndStopped"] = fi(und_stop)
    M[f"R{prefix}UndOther"] = fi(und_oth)
    M[f"R{prefix}DetMed"] = f(get(fr, "detection_ms_all.median"), 0)
    M[f"R{prefix}DetPNineFive"] = f(get(fr, "detection_ms_all.p95"), 0)
    M[f"R{prefix}DetMax"] = f(get(fr, "detection_ms_all.max"), 0)
    M[f"R{prefix}Avail"] = f(get(fr, "availability.availability"), 1, 100)
    M[f"R{prefix}Thr"] = f(get(fr, "availability.throughput_weighted"), 1, 100)
    M[f"R{prefix}Cycles"] = fi(get(fr, "availability.cycles"))
    r = "reliability."
    M[f"R{prefix}ExposureH"] = f(get(fr, r + "exposure_h"), 1)
    M[f"R{prefix}SAEvents"] = fi(get(fr, r + "service_affecting_events"))
    M[f"R{prefix}OpEvents"] = fi(get(fr, r + "operator_intervention_events"))
    M[f"R{prefix}SARate"] = fsig(get(fr, r + "rate_service_affecting_per_h"), 3)
    M[f"R{prefix}SARateCI"] = fci(get(fr, r + "rate_ci95.0"), get(fr, r + "rate_ci95.1"), 2)
    M[f"R{prefix}OpRate"] = fsig(get(fr, r + "rate_operator_per_h"), 3)
    M[f"R{prefix}OpRateCI"] = fci(get(fr, r + "rate_operator_ci95.0"), get(fr, r + "rate_operator_ci95.1"), 3)
    sa = get(fr, r + "rate_service_affecting_per_h")
    op = get(fr, r + "rate_operator_per_h")
    M[f"R{prefix}SAMTBF"] = fsig(1 / sa, 3) if ok(sa) and sa > 0 else MISSING
    M[f"R{prefix}OpMTBF"] = fsig(1 / op, 3) if ok(op) and op > 0 else MISSING
    M[f"R{prefix}IntComplete"] = fi(get(fr, r + "intervals.complete"))
    M[f"R{prefix}IntCensored"] = fi(get(fr, r + "intervals.censored"))
    M[f"R{prefix}WeibullShape"] = f(get(fr, r + "weibull.shape"), 2)
    M[f"R{prefix}WeibullScale"] = fsig(get(fr, r + "weibull.scale_h"), 3)
    M[f"R{prefix}WeibullKSp"] = f(get(fr, r + "weibull.ks_p_complete_only"), 2)
    _p = get(fr, r + "weibull.ks_p_complete_only")
    M[f"R{prefix}WeibullKSpText"] = MISSING if _p is None else (r"$p<0.001$" if _p < 0.001 else f"$p={_p:.3f}$")
    short = {"tracking_loss": "Track", "sensor_timeout": "Stream", "computational_overrun": "Overrun",
             "hardware_communication": "Comm", "configuration_inconsistency": "Config", "network_partition": "Part",
             "constraint_violation": "Lunge", "memory_allocation": "Mem"}
    for k, n in short.items():
        c = pc.get(k) or {}
        if c.get("detection_ms_median") is not None:
            M[f"R{prefix}DetMed{n}"] = f(c["detection_ms_median"], 0)
            M[f"R{prefix}DetMax{n}"] = f(c["detection_ms_max"], 0)
    if table_name and not pc:
        T[table_name] = [row(label, *([MISSING] * 8)) for _, label in CATS]
    elif table_name:
        rows = []
        for k, label in CATS:
            c = pc.get(k, {})
            rows.append(row(label, fi(c.get("injected")) if c else "0", fi(c.get("detected")) if c else "0",
                            fi(c.get("undetected_while_stopped")) if c else "0", fi(c.get("undetected_other")) if c else "0",
                            f(c.get("detection_ms_median"), 0) if c.get("detection_ms_median") is not None else "--",
                            f(c.get("detection_ms_max"), 0) if c.get("detection_ms_max") is not None else "--",
                            fsig(c.get("recovery_s_median"), 2) if c.get("recovery_s_median") is not None else "--",
                            "yes" if c.get("operator_intervention_class") else "no"))
        T[table_name] = rows
    if rel_table and not fr:
        T[rel_table] = [row(label, MISSING, MISSING, MISSING) for _, label in CATS]
    elif rel_table:
        rows = []
        per = get(fr, r + "per_category", {}) or {}
        for k, label in CATS:
            label = label.replace(" (lunge)", "")  # episodes include violations not caused by an injected lunge
            if k == "configuration_inconsistency":  # rejected configurations are not service-affecting episodes
                rows.append(row(label, "n/a", "n/a", "n/a"))
                continue
            c = per.get(k)
            if not c:
                rows.append(row(label, "0", "0", "--"))
                continue
            rows.append(row(label, fi(c["events"]), fsig(c["rate_per_h"], 3), fci(c["ci95"][0], c["ci95"][1], 3)))
        T[rel_table] = rows


def sensitivity_table(extra, M, T):
    rows = []
    sc = (extra or {}).get("sensitivity_by_config") or []
    order = {"poisson": 0, "clustered": 1, "weibull": 2}
    name = lambda s: ("Poisson" if s["arrival"] == "poisson" else "Clustered (Neyman--Scott)" if s["arrival"] == "clustered"
                      else f"Weibull renewal, $k={s['weibull_shape']}$")
    for s in sorted(sc, key=lambda s: (order.get(s["arrival"], 9), s.get("weibull_shape") or 0, s["rate_scale"])):
        rows.append(row(name(s), f"{s['rate_scale']:.1f}", fi(s["injected"]), fi(s["service_affecting_events"]),
                        fsig(s["rate_service_affecting_per_h"], 3), f(s["availability"], 1, 100), f(s["throughput_weighted"], 1, 100)))
    if not rows:
        rows = [row(MISSING, *([MISSING] * 6))]
    T["tab_sensitivity"] = rows
    if sc:
        av = [s["availability"] for s in sc]
        M["RSensAvailMin"] = f(min(av), 1, 100)
        M["RSensAvailMax"] = f(max(av), 1, 100)
    else:
        M["RSensAvailMin"] = MISSING
        M["RSensAvailMax"] = MISSING


def tuning_compare(res, M, T):
    sel = res.get("tuning_selection") or {}
    rows = []
    for k in ("proposed", "hc_cbf", "ssm", "pf"):
        s = sel.get(k)
        if not s:
            rows.append(row(STRAT[k], MISSING, MISSING, MISSING, MISSING, MISSING))
            continue
        rows.append(row(STRAT[k], PARAM_TEX.get(s["parameter"], s["parameter"]), f"{s['value']:g}",
                        f(s["mean_task_cycle_s"], 2), fi(s["min_sep_m"] * 1000), fi(s["segments"])))
        M["RTune" + STRAT_SHORT[k].replace("-", "") + "Value"] = f"{s['value']:g}"
    T["tab_tuning"] = rows
    M["RTuneStrategiesSelected"] = fi(len(sel)) if sel else MISSING
    bc = res.get("baseline_comparison") or {}
    rr = bc.get("rows") or []
    M["RCmpHypotheses"] = fi(bc.get("hypotheses"))
    rows = []
    sig = 0
    for ep, unit, scale, nd in (("task_cycle_s", "s", 1, 2), ("min_sep_m", "mm", 1000, 0)):
        for b in ("hc_cbf", "ssm", "pf"):
            r = next((x for x in rr if x["endpoint"] == ep and x["baseline"] == b), None)
            epl = "Task cycle (s)" if ep == "task_cycle_s" else "Min.\\ separation (mm)"
            if not r:
                rows.append(row(epl, STRAT_SHORT[b], MISSING, MISSING, MISSING, MISSING, MISSING, MISSING))
                continue
            sig += int(r["p_holm"] < 0.05)
            rows.append(row(epl, STRAT_SHORT[b], f"{f(r['proposed_mean'], nd, scale)} $\\pm$ {f(r['proposed_sd'], nd, scale)}",
                            f"{f(r['baseline_mean'], nd, scale)} $\\pm$ {f(r['baseline_sd'], nd, scale)}",
                            f"{f(r['mean_diff'], nd, scale)} {fci(r['ci95'][0], r['ci95'][1], nd, scale)}",
                            f(r["d_z"], 2) if r["d_z"] is not None else "--", fp(r["p"]), fp(r["p_holm"])))
            key = ("Cyc" if ep == "task_cycle_s" else "Sep") + STRAT_SHORT[b].replace("-", "")
            M[f"RCmp{key}Diff"] = f(r["mean_diff"], nd, scale)
            M[f"RCmp{key}CI"] = fci(r["ci95"][0], r["ci95"][1], nd, scale)
            M[f"RCmp{key}PHolm"] = fp(r["p_holm"])
            M[f"RCmp{key}Dz"] = f(r["d_z"], 2) if r["d_z"] is not None else MISSING
            M[f"RCmp{key}N"] = fi(r["n"])
    T["tab_compare"] = rows
    M["RCmpSignificant"] = fi(sig) if rr else MISSING


def protocol(res, M, T):
    p = res.get("protocol") or {}
    run = p[sorted(p)[0]] if p else {}
    rows = []
    for k, label in (("modbus", "Modbus TCP (FC01, FC03, FC06)"), ("rest", "REST (GET /api/v1/status)")):
        c = run.get(k, {})
        rows.append(row(label, fi(c.get("n")), f(c.get("median_ms"), 3), f(c.get("p95_ms"), 3), f(c.get("p99_ms"), 3),
                        fi(c.get("failed"))))
        key = "Modbus" if k == "modbus" else "Rest"
        M[f"RProt{key}N"] = fi(c.get("n"))
        M[f"RProt{key}Med"] = f(c.get("median_ms"), 3)
        M[f"RProt{key}PNineNine"] = f(c.get("p99_ms"), 3)
        M[f"RProt{key}Failed"] = fi(c.get("failed"))
    T["tab_protocol"] = rows


def conformance(res, M, T):
    c = res.get("conformance") or {}
    run = c[sorted(c)[0]] if c else {}
    M["RConfPass"] = fi(run.get("pass"))
    M["RConfFail"] = fi(run.get("fail"))
    M["RConfNotRun"] = fi(run.get("not_run"))
    items = run.get("items") or []
    M["RConfItems"] = fi(len(items)) if items else MISSING
    M["RConfInfo"] = fi(sum(1 for i in items if i["result"] == "info")) if items else MISSING
    M["RConfVersion"] = run.get("controller_version") or MISSING
    for k in ("RConfURSixObserved", "RConfURElevenObserved", "RConfURTenObserved", "RConfURElevenMs", "RConfURTenMs"):
        M[k] = MISSING
    rows = []
    esc = lambda s: (s.replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
                     .replace("#", r"\#").replace("+/-", r"$\pm$").replace("^2", r"$^2$").replace(">=", r"$\geq$"))
    brk = lambda s: s.replace(",", r",\allowbreak{}").replace(r"\_", r"\_\allowbreak{}")
    for i in sorted(items, key=lambda i: int(i["item_id"].split("-")[1])):
        rows.append(row(i["item_id"], brk(esc(i["document_clause"])), brk(esc(i["expected"])), brk(esc(i["observed"])),
                        esc(i["result"])))
        if i["item_id"] == "UR-06":
            M["RConfURSixObserved"] = esc(i["observed"])
        if i["item_id"] == "UR-11":
            M["RConfURElevenObserved"] = esc(i["observed"])
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ms", i["observed"])
            M["RConfURElevenMs"] = m.group(1) if m else MISSING
        if i["item_id"] == "UR-10":
            M["RConfURTenObserved"] = esc(i["observed"])
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ms", i["observed"])
            M["RConfURTenMs"] = m.group(1) if m else MISSING
    T["tab_conformance"] = rows or [row(MISSING, MISSING, MISSING, MISSING, MISSING)]


def cbf(res, M):
    c = res.get("cbf_training") or {}
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


def extra_sections(extra, M, T):
    ex = extra or {}
    cm = ex.get("code_metrics") or {}
    M["RCodeShared"] = fi(cm.get("shared_loc"))
    for k, n in (("ur_rtde", "UR"), ("kuka_fri", "KUKA"), ("abb_egm", "ABB")):
        M[f"RCode{n}"] = fi((cm.get("adapter_loc") or {}).get(k))
    M["RCodeFunctions"] = fi(cm.get("functions"))
    M["RCodeCCNMean"] = f(cm.get("ccn_mean"), 1)
    M["RCodeCCNMax"] = fi(cm.get("ccn_max"))
    M["RCodeCCNOverTen"] = fi(cm.get("ccn_over_10"))
    ib = (ex.get("injection_breakdown") or {})
    comm = ib.get("comm_by_param") or {}
    short = sum(v["injected"] for k, v in comm.items() if k in ("1", "2"))
    short_det = sum(v["detected"] for k, v in comm.items() if k in ("1", "2"))
    long_ = sum(v["injected"] for k, v in comm.items() if k in ("3", "4", "5"))
    long_det = sum(v["detected"] for k, v in comm.items() if k in ("3", "4", "5"))
    M["RCommShortInj"] = fi(short) if comm else MISSING
    M["RCommShortDet"] = fi(short_det) if comm else MISSING
    M["RCommLongInj"] = fi(long_) if comm else MISSING
    M["RCommLongDet"] = fi(long_det) if comm else MISSING
    lu = ib.get("lunge") or {}
    M["RLungeInj"] = fi(lu.get("injected"))
    M["RLungeCrossed"] = fi(lu.get("floor_crossed_latched"))
    M["RLungeHeld"] = fi(lu.get("floor_held"))
    M["RLungeWhileStopped"] = fi(lu.get("while_stopped"))
    for camp, P in (("timing_behaviour", "RBehTim"), ("compare_behaviour", "RBehCmp"), ("injection_behaviour", "RBehInj")):
        b = ex.get(camp) or {}
        mf = b.get("mode_fraction") or {}
        M[P + "Nominal"] = f(mf.get("nominal"), 2, 100)
        stopped = sum(mf.get(k, 0) for k in ("protective_stop", "protective_stop_latched", "emergency_stop")) if mf else None
        M[P + "Stopped"] = f(stopped, 2, 100)
        degraded = sum(mf.get(k, 0) for k in ("low_confidence", "degraded_stream", "geometric_fallback", "overrun_shed")) if mf else None
        M[P + "Degraded"] = f(degraded, 2, 100)
        fc = b.get("flag_counts") or {}
        M[P + "QpRelaxed"] = fi(fc.get("qp_relaxed"))
        M[P + "QpFailed"] = fi(fc.get("qp_failed"))
        M[P + "BelowFloor"] = fi(b.get("cycles_below_active_floor"))
        M[P + "BelowViol"] = fi(b.get("cycles_below_floor_by_more_than_0_05m"))
        M[P + "MinSepMm"] = f(b.get("min_separation_m"), 0, 1000)
        ps = (b.get("by_strategy") or {}).get("proposed") or {}
        M[P + "LearnedPct"] = f(ps["learned_rows"] / ps["cycles"], 1, 100) if ps.get("cycles") else MISSING
    ld = ex.get("logger_drops") or {}
    M["RLogCyclesDropped"] = fi(ld.get("cycles_dropped")) if ld else MISSING
    M["RLogEventsDropped"] = fi(ld.get("events_dropped")) if ld else MISSING
    M["RLogRuns"] = fi(ld.get("runs")) if ld else MISSING
    blocks = (ex.get("timing_behaviour") or {}).get("blocks") or []
    if blocks:
        mx = sorted(b["exec_max_ms"] for b in blocks)
        M["RBlkMaxMedian"] = f(mx[len(mx) // 2], 2)
        M["RBlkMaxMax"] = f(mx[-1], 2)
        M["RBlkOverOne"] = fi(sum(1 for x in mx if x > 1.0))
        M["RBlkOverTen"] = fi(sum(1 for x in mx if x > 10.0))
    else:
        for k in ("RBlkMaxMedian", "RBlkMaxMax", "RBlkOverOne", "RBlkOverTen"):
            M[k] = MISSING


def closure_sections(res, extra, bf, M):
    """Numbers added at the closure (28.10.2026) for the interpretations of the results; every one is
    computed here from results.json, results_extra.json or below_floor.json (supplementary S6)."""
    ex = extra or {}
    # --- S6: cycles below the active floor, by episode
    def cls(lst):
        return {k: [e for e in lst if e["mode_first"] == k] for k in (0, 3, 6)}
    if bf:
        for camp, P in (("timing_campaign", "RBfTim"), ("baseline_compare", "RBfCmp"), ("fault_injection", "RBfInj")):
            b = bf.get(camp) or {}
            lst = b.get("list") or []
            lunge = [e for e in lst if e["last_lunge_dt_s"] is not None and e["last_lunge_dt_s"] <= 3.0]
            other = [e for e in lst if e not in lunge]
            M[P + "Ep"] = fi(len(lst)); M[P + "Cycles"] = fi(sum(e["cycles"] for e in lst))
            M[P + "LungeEp"] = fi(len(lunge)); M[P + "LungeCycles"] = fi(sum(e["cycles"] for e in lunge))
            M[P + "OtherEp"] = fi(len(other)); M[P + "OtherCycles"] = fi(sum(e["cycles"] for e in other))
            M[P + "ZeroAll"] = fi(sum(1 for e in lst if e["zero_speed_cycles_before"] > 0))
            M[P + "LungeNeg"] = fi(sum(1 for e in lunge if e["min_sep_m"] < 0))
            z = sorted(e["zero_speed_cycles_before"] for e in lunge)
            if z:  # defined only where lunges crossed the floor (a missing one would print ??)
                M[P + "LungeZeroMinMs"] = fi(20 * z[0])
                M[P + "LungeZeroMedMs"] = fi(20 * z[len(z) // 2])
                M[P + "LungeDtMaxMs"] = fi(round(1000 * max(e["last_lunge_dt_s"] for e in lunge)))
            for k, name in ((0, "Nom"), (3, "Fb"), (6, "Lat")):
                g = cls(other)[k]
                M[P + name + "Ep"] = fi(len(g)); M[P + name + "Cycles"] = fi(sum(e["cycles"] for e in g))
                if g:
                    M[P + name + "SepMinMm"] = fi(round(1000 * min(e["min_sep_m"] for e in g)))
                    M[P + name + "SepMaxMm"] = fi(round(1000 * max(e["min_sep_m"] for e in g)))
                    M[P + name + "ZeroMinMs"] = fi(20 * min(e["zero_speed_cycles_before"] for e in g))
                    M[P + name + "Viol"] = fi(sum(1 for e in g if e["min_sep_m"] < e["floor_m"] - 0.05))
    # --- ablation per run: idle versus loaded host
    ar = ex.get("ablation_runs") or []
    if ar:
        def med(v):
            v = sorted(v); n = len(v)
            return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])
        by = {}
        for r in ar:
            by.setdefault((r["configuration"], r["load"]), []).append(r)
        idle_meds = {c: med([r["median_ms"] for r in by[(c, "idle")]]) for c, _ in ABL if (c, "idle") in by and c != "A1"}
        load_meds = {c: med([r["median_ms"] for r in by[(c, "load")]]) for c, _ in ABL if (c, "load") in by}
        M["RAblIdleMedMinUs"] = fi(round(1000 * min(idle_meds.values())))
        M["RAblIdleMedMaxUs"] = fi(round(1000 * max(idle_meds.values())))
        lm = {c: v for c, v in load_meds.items() if c != "A1"}
        M["RAblLoadMedMinUs"] = fi(round(1000 * min(lm.values())))
        M["RAblLoadMedMaxUs"] = fi(round(1000 * max(lm.values())))
        M["RAblAThreeIdleMedUs"] = fi(round(1000 * idle_meds["A3"]))
        M["RAblAOneIdleMedUs"] = fi(round(1000 * med([r["median_ms"] for r in by[("A1", "idle")]])))
        M["RAblAOneLoadMedUs"] = fi(round(1000 * med([r["median_ms"] for r in by[("A1", "load")]])))
        M["RAblAThreeLoadMedUs"] = fi(round(1000 * load_meds["A3"]))
        def mx(c, l): return max(r["max_ms"] for r in by[(c, l)])
        def medmx(c, l): return med([r["max_ms"] for r in by[(c, l)]])
        def sdr(c, l): return med([r["sd_release_ms"] for r in by[(c, l)]])
        M["RAblATwoLoadMaxMed"] = f(medmx("A2", "load"), 2)
        M["RAblATwoLoadMax"] = f(mx("A2", "load"), 2)
        M["RAblATwoLoadSDRelUs"] = fi(round(1000 * sdr("A2", "load")))
        M["RAblAThreeLoadSDRelUs"] = fi(round(1000 * sdr("A3", "load")))
        M["RAblAThreeLoadMax"] = f(mx("A3", "load"), 2)
        M["RAblSingleLoadMax"] = f(max(mx(c, "load") for c in ("A2a", "A2b", "A2c")), 2)
        M["RAblATwoIdleMax"] = f(mx("A2", "idle"), 2)
        M["RAblAThreeIdleMax"] = f(mx("A3", "idle"), 2)
        M["RAblAZeroIdleMax"] = f(mx("A0", "idle"), 2)
        M["RAblAZeroLoadMax"] = f(mx("A0", "load"), 2)
        M["RAblAOneIdleMax"] = f(mx("A1", "idle"), 2)
    # --- per-block maxima against the block's 99th percentile and the background load
    blocks = (ex.get("timing_behaviour") or {}).get("blocks") or []
    if blocks:
        r = sorted(b["exec_max_ms"] / b["exec_p99_ms"] for b in blocks)
        M["RBlkMaxToPNineNine"] = f(r[len(r) // 2], 1)
        xs = [b["load_duty"] for b in blocks]; ys = [b["exec_max_ms"] for b in blocks]
        n = len(xs); mxv = sum(xs) / n; myv = sum(ys) / n
        cov = sum((a - mxv) * (b - myv) for a, b in zip(xs, ys))
        sx = math.sqrt(sum((a - mxv) ** 2 for a in xs)); sy = math.sqrt(sum((b - myv) ** 2 for b in ys))
        M["RBlkMaxLoadCorr"] = f(cov / (sx * sy), 2) if sx and sy else MISSING
    # --- sensitivity: availability against the number of operator-intervention events
    sc = ex.get("sensitivity_by_config") or []
    if sc:
        op0 = [c["availability"] for c in sc if c["operator_intervention_events"] == 0]
        M["RSensNoOpConfigs"] = fi(len(op0))
        M["RSensNoOpAvailMin"] = f(min(op0), 1, 100) if op0 else MISSING
        M["RSensNoOpAvailMax"] = f(max(op0), 1, 100) if op0 else MISSING
        M["RSensNoOpLossMaxPct"] = f(1 - min(op0), 1, 100) if op0 else MISSING
        top = max(sc, key=lambda c: c["operator_intervention_events"])
        M["RSensOpMax"] = fi(top["operator_intervention_events"])
        M["RSensOpMaxAvail"] = f(top["availability"], 1, 100)
        xs = [c["operator_intervention_events"] for c in sc]; ys = [100 * c["availability"] for c in sc]
        n = len(xs); mxv = sum(xs) / n; myv = sum(ys) / n
        sxx = sum((a - mxv) ** 2 for a in xs)
        M["RSensSlopePct"] = f(-sum((a - mxv) * (b - myv) for a, b in zip(xs, ys)) / sxx, 1) if sxx else MISSING
        M["RSensThrMin"] = f(min(c["throughput_weighted"] for c in sc), 1, 100)
        M["RSensThrMax"] = f(max(c["throughput_weighted"] for c in sc), 1, 100)
    # --- absolute values of signed paired differences, for sentences that state the direction in words
    for k in [k for k in list(M.m) if k.startswith("RCmp") and k.endswith("Diff")]:
        v = M.m[k]
        if v != MISSING:
            M[k + "Abs"] = v.lstrip("-")
    # --- injection campaign: undetected faults by cause
    rows = ((res or {}).get("fault_injection") or {}).get("rows") or []
    if rows:
        stop = {5, 6, 7}
        M["RFiStreamUndActive"] = fi(sum(1 for x in rows if x["category"] == "sensor_timeout" and not x["detected"]
                                         and x["mode_at_injection"] == 2))
        M["RCommShortStopped"] = fi(sum(1 for x in rows if x["category"] == "hardware_communication" and not x["detected"]
                                        and x["mode_at_injection"] in stop))
        M["RCommShortOther"] = fi(sum(1 for x in rows if x["category"] == "hardware_communication" and not x["detected"]
                                      and x["mode_at_injection"] not in stop))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--extra", default="")
    ap.add_argument("--below", default="", help="below_floor.json (supplementary S6)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res, extra, prov = {}, {}, []
    if Path(a.results).exists():
        res = json.loads(Path(a.results).read_text())
        prov.append(f"results.json sha256 {hashlib.sha256(Path(a.results).read_bytes()).hexdigest()}")
    else:
        prov.append("results.json ABSENT: every number prints as ??")
    if a.extra and Path(a.extra).exists():
        extra = json.loads(Path(a.extra).read_text())
        prov.append(f"results_extra.json sha256 {hashlib.sha256(Path(a.extra).read_bytes()).hexdigest()}")
    else:
        prov.append("results_extra.json ABSENT")
    bf = {}
    if a.below and Path(a.below).exists():
        bf = json.loads(Path(a.below).read_text())
        prov.append(f"below_floor.json sha256 {hashlib.sha256(Path(a.below).read_bytes()).hexdigest()}")
    M, T = Macros(), {}
    timing(res, M, T)
    ablation(res, extra, M, T)
    faults_section(res, "Fi", "fault_injection", M, T, table_name="tab_faults")
    faults_section(res, "Ft", "faults_in_timing_campaign", M, T, rel_table="tab_reliability")
    faults_section(res, "Fs", "fault_sensitivity", M, T)
    sensitivity_table(extra, M, T)
    tuning_compare(res, M, T)
    protocol(res, M, T)
    conformance(res, M, T)
    cbf(res, M)
    extra_sections(extra, M, T)
    closure_sections(res, extra, bf, M)
    header = "% generated by scripts/make_numbers.py -- do not edit\n% " + "\n% ".join(prov)
    (out / "r3_numbers.tex").write_text(M.tex(header))
    for name, rows in T.items():
        (out / f"{name}.tex").write_text(header + "\n" + "\n".join(typeset_minus(r) for r in rows) + "\n")
    (out / "provenance.txt").write_text("\n".join(prov) + "\n")
    n_missing = sum(1 for v in M.m.values() if v == MISSING)
    print(f"{len(M.m)} macros ({n_missing} missing), {len(T)} tables -> {out}")


if __name__ == "__main__":
    main()
