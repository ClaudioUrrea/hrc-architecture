"""PLC commissioning time (Section 6.1, Table 6, Figure 5)."""
import csv, json, statistics as st

QUOTATIONS_H = {"siemens": (42, 8), "rockwell": (45, 10), "mitsubishi": (40, 7)}


def main(path="data/plc_runs.csv"):
    runs = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            runs.setdefault(row["platform"], []).append(float(row["hours"]))
    out = {}
    for k, v in runs.items():
        custom, spread = QUOTATIONS_H[k]
        out[k] = {"runs": len(v), "mean_h_measured": round(st.mean(v), 2),
                  "sd_h": round(st.stdev(v), 2),
                  "custom_h_estimated": custom, "quotation_spread_h": spread,
                  "ratio": round(custom / st.mean(v), 1)}
    means = [o["mean_h_measured"] for o in out.values()]
    out["mean"] = {"modular_h_measured": round(st.mean(means), 2),
                   "custom_h_estimated": round(st.mean([q[0] for q in QUOTATIONS_H.values()]), 2)}
    out["mean"]["ratio"] = round(out["mean"]["custom_h_estimated"] / out["mean"]["modular_h_measured"], 1)
    out["mean"]["reduction_pct"] = round(100 * (1 - out["mean"]["modular_h_measured"] /
                                                out["mean"]["custom_h_estimated"]), 1)
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
