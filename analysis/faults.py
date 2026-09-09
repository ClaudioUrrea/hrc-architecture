"""Fault campaign and availability (Section 8, Table 7, Figure 7)."""
import csv, json
from collections import Counter

T_MIN = 12000.0                 # 200 h
MEAN_AUTOMATED_RECOVERY_S = 3.5
MEAN_OPERATOR_INTERVENTION_MIN = 28.4
DEGRADED_MIN, DEGRADED_ALPHA = 320.0, 0.65


def main(path="data/faults_450.csv"):
    cats, sa, oi = Counter(), 0, 0
    with open(path) as fh:
        for row in csv.DictReader(fh):
            cats[row["category"]] += 1
            sa += row["service_affecting"] == "yes"
            oi += row["operator_intervention"] == "yes"
    total = sum(cats.values())
    automated = sa - oi
    downtime = automated * MEAN_AUTOMATED_RECOVERY_S / 60 + oi * MEAN_OPERATOR_INTERVENTION_MIN
    a = (T_MIN - downtime) / T_MIN
    a_w = a - (1 - DEGRADED_ALPHA) * DEGRADED_MIN / T_MIN
    return {"events_total": total, "by_category": dict(cats),
            "service_affecting": sa, "operator_intervention": oi,
            "automatically_recovered": automated,
            "downtime_min": round(downtime, 1),
            "availability": round(a, 4), "availability_weighted": round(a_w, 4),
            "caveat": "property of the injected fault model, not of an installed cell"}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
