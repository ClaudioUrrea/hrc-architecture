"""PLC commissioning time (Section 6.1, Table 8, Figure 5).

The modular times are MEASURED: they are read from data/plc_runs.csv.
The bespoke-integration figure is NOT measured and NOT a third-party quotation:
it is the author's own estimate of 40-45 h for the same task. No documentary
record of it exists, so it is carried here as one range that applies to the task,
not as per-platform values, and no conclusion rests on it.
"""
import csv, json, statistics as st

BESPOKE_ESTIMATE_H = (40.0, 45.0)   # author's undocumented estimate (class E)


def main(path="data/plc_runs.csv"):
    runs = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            runs.setdefault(row["platform"], []).append(float(row["hours"]))
    out = {}
    for k, v in runs.items():
        out[k] = {"runs": len(v), "mean_h_measured": round(st.mean(v), 2),
                  "sd_h": round(st.stdev(v), 2)}
    means = [o["mean_h_measured"] for o in out.values()]
    lo, hi = BESPOKE_ESTIMATE_H
    m = round(st.mean(means), 2)
    out["mean"] = {"modular_h_measured": m,
                   "bespoke_h_estimate_lo": lo, "bespoke_h_estimate_hi": hi,
                   "ratio_lo": round(lo / m, 1), "ratio_hi": round(hi / m, 1)}
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
