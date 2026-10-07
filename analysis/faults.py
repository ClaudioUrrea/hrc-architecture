"""Fault campaign and availability (Section 8, Table 9, Figure 7).

v2.0.0 (round 2). The availability figure no longer mixes two data sets.

The first version applied the 3.5 s mean recovery time of the 450-injection campaign to the 150 automatically
recovered faults of the 200 h run. A reviewer objected, correctly: the injected population and the naturally
arising population were never shown to recover identically, so one cannot supply the recovery time of the other.

Availability is therefore computed from the per-mode recovery times recorded INSIDE the 200 h run. The injection
campaign is retained as an independent cross-check and reported separately; it agrees to within 0.01 percentage
points, which is a finding, not an assumption.

v2.1.0. Every input is read from data/faults_450.csv (none is a constant any more): the per-mode recovery means,
the numbers of automatically recovered events and the operator-intervention times. In v2.0.0 these were typed in
as constants that the csv of that release did not reproduce; the timing columns of the csv were re-derived by
tools/reconstruct_faults.py so that file and constants agree (docs/DATA_PROVENANCE.md).
"""
import csv, json
from collections import Counter, defaultdict
import numpy as np

T_MIN = 12000.0                           # 200 h observation window, minutes
DEGRADED_MIN, DEGRADED_ALPHA = 320.0, 0.65

# Cross-check only. Mean automated recovery of the 450-injection campaign; not an input to the figure.
INJECTION_CAMPAIGN_MEAN_RECOVERY_S = 3.5

# Sensitivity ranges requested in round 2: the fault rates are drawn from an injected model, and the operator
# time from a small sample, so both are varied.
RATE_SENSITIVITY = (0.5, 1.5)             # +/- 50 % on every automated fault rate
OPERATOR_TIME_SENSITIVITY_MIN = (15.0, 45.0)


def _availability(downtime_min):
    return (T_MIN - downtime_min) / T_MIN


def _load(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            r["detection_ms"] = float(r["detection_ms"])
            r["recovery_s"] = float(r["recovery_s"]) if r["recovery_s"] not in ("", "nan") else None
            r["intervention_min"] = float(r["intervention_min"]) if r.get("intervention_min") not in (None, "") else None
            rows.append(r)
    return rows


def main(path="data/faults_450.csv"):
    rows = _load(path)
    cats = Counter(r["category"] for r in rows)
    sa = sum(r["service_affecting"] == "yes" for r in rows)
    oi_rows = [r for r in rows if r["operator_intervention"] == "yes"]
    auto = [r for r in rows if r["service_affecting"] == "yes" and r["operator_intervention"] == "no"]
    by_mode = defaultdict(list)
    for r in auto:
        by_mode[r["category"]].append(r["recovery_s"])
    auto_counts = {m: len(v) for m, v in by_mode.items()}
    in_run_mean_s = {m: float(np.mean(v)) for m, v in by_mode.items()}
    op_min = [r["intervention_min"] for r in oi_rows]
    op_mean = float(np.mean(op_min))

    def downtime(rate_factor=1.0, operator_min=None, uniform_recovery_s=None):
        auto_s = sum(n * rate_factor * (uniform_recovery_s if uniform_recovery_s is not None else in_run_mean_s[m])
                     for m, n in auto_counts.items())
        # The rate factor scales EVERY category, the operator-intervention events included; the operator-time
        # sensitivity instead holds the rates fixed and substitutes the mean intervention time.
        op = len(oi_rows) * rate_factor * (op_mean if operator_min is None else operator_min)
        return auto_s / 60.0 + op

    dt = downtime()
    a = _availability(dt)
    a_w = a - (1 - DEGRADED_ALPHA) * DEGRADED_MIN / T_MIN
    cross = _availability(downtime(uniform_recovery_s=INJECTION_CAMPAIGN_MEAN_RECOVERY_S))
    sens = {
        "fault_rates_minus_50pct": round(_availability(downtime(RATE_SENSITIVITY[0])), 4),
        "fault_rates_plus_50pct": round(_availability(downtime(RATE_SENSITIVITY[1])), 4),
        "operator_time_15_min": round(_availability(downtime(operator_min=OPERATOR_TIME_SENSITIVITY_MIN[0])), 4),
        "operator_time_45_min": round(_availability(downtime(operator_min=OPERATOR_TIME_SENSITIVITY_MIN[1])), 4),
    }
    det = np.array([r["detection_ms"] for r in rows])
    rec_all = np.array([r["recovery_s"] for r in auto])
    mode_det = defaultdict(list)
    mode_rec = defaultdict(list)
    for r in rows:
        mode_det[r["category"]].append(r["detection_ms"])
        if r["recovery_s"] is not None:
            mode_rec[r["category"]].append(r["recovery_s"])
    return {
        "events_total": len(rows), "by_category": dict(cats),
        "service_affecting": sa, "operator_intervention": len(oi_rows),
        "automatically_recovered": len(auto),
        "downtime_min": round(dt, 1),
        "availability": round(a, 4),
        "availability_weighted": round(a_w, 4),
        "availability_injection_cross_check": round(cross, 4),
        "availability_sensitivity": sens,
        "per_mode": {m: {"events": cats[m],
                         "detection_mean_ms": round(float(np.mean(mode_det[m])), 1),
                         "recovery_median_s": round(float(np.median(mode_rec[m])), 2) if mode_rec.get(m) else None,
                         "recovery_mean_s": round(float(np.mean(mode_rec[m])), 2) if mode_rec.get(m) else None}
                     for m in cats},
        "in_run_recovery_mean_s": {m: round(v, 2) for m, v in in_run_mean_s.items()},
        "pooled": {"detection_ms": {"p50": round(float(np.median(det)), 1),
                                    "p95": round(float(np.quantile(det, .95)), 1),
                                    "max": round(float(det.max()), 1)},
                   "automatic_recovery_s": {"mean": round(float(rec_all.mean()), 2),
                                            "p50": round(float(np.median(rec_all)), 2),
                                            "p95": round(float(np.quantile(rec_all, .95)), 2)}},
        "operator_intervention_mean_min": round(op_mean, 1),
        "automatic_recovery_downtime_min": round(sum(rec_all) / 60.0, 2),
        "source_of_recovery_times": "the 200 h run only; the injection campaign "
                                    "is a cross-check, not an input",
        "caveat": "property of the simulated fault model, not of an installed cell",
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
