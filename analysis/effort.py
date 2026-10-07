"""Adaptation effort (Section 5.3, Appendix C, Figure 3b).

The measured rows were produced by the architecture's own author, familiar with
the code base, working against software simulators. They are therefore a LOWER
bound on what an unfamiliar team would need, and the ratio against the estimated
monolithic alternative is an UPPER bound on what a third party should expect.
"""
import csv, json

MONOLITHIC = {"loc_touched": (8000, 10000), "productivity_loc_per_h": (40, 50)}


def main(path="data/effort_log.csv"):
    per = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            if row["counted"] == "yes":
                per[row["platform"]] = per.get(row["platform"], 0.0) + float(row["hours"])
    lo = MONOLITHIC["loc_touched"][0] / MONOLITHIC["productivity_loc_per_h"][1]
    hi = MONOLITHIC["loc_touched"][1] / MONOLITHIC["productivity_loc_per_h"][0]
    return {"measured_h": per, "evidence_class_measured": "M",
            "monolithic_estimate_h": [round(lo), round(hi)],
            "monolithic_value_used_h": 225, "evidence_class_estimate": "E",
            "ratio_range": [round(lo / max(per.values()), 1), round(hi / min(per.values()), 1)]}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
