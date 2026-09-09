"""Assert that recomputed values match the values printed in the paper.

Exits non-zero on the first disagreement. Tolerances are the rounding used in
the manuscript, not free parameters.
"""
import argparse, json, sys

EXPECTED = [
    ("timing.serial_critical_path_ms", 6.2, 0.01),
    ("timing.miss_probability_upper_bound_95", 8.3e-8, 1e-9),
    ("plc_time.mean.modular_h_measured", 3.67, 0.01),
    ("plc_time.mean.custom_h_estimated", 42.33, 0.01),
    ("plc_time.mean.reduction_pct", 91.3, 0.2),
    ("faults.events_total", 166, 0),
    ("faults.service_affecting", 156, 0),
    ("faults.operator_intervention", 6, 0),
    ("faults.availability", 0.9851, 0.0005),
    ("reliability.populations.all_faults.mtbf_h", 1.20, 0.01),
    ("reliability.populations.service_affecting.mtbf_h", 1.28, 0.01),
    ("reliability.populations.operator_intervention.mtbf_h", 33.33, 0.01),
    ("reliability.weibull.shape", 1.02, 0.05),
    ("ablation.median_cost_of_architecture_ms", 0.3, 0.01),
]


def dig(d, path):
    for part in path.split("."):
        d = d[part]
    return d


def main(path):
    results = json.load(open(path))
    bad = 0
    for key, want, tol in EXPECTED:
        got = dig(results, key)
        ok = abs(got - want) <= tol
        print(f"{'OK  ' if ok else 'FAIL'}  {key}: got {got}, paper says {want}")
        bad += not ok
    if bad:
        sys.exit(f"{bad} value(s) disagree with the manuscript")
    print("all checked values agree with the manuscript")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="out/results.json")
    main(ap.parse_args().results)
