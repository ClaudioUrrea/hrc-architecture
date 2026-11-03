#!/usr/bin/env python3
"""Compute every reported quantity from raw run directories and write results.json.

    python3 analysis/report.py --runs runs [--out results] [--allow-non-rt]

results.json lists, for each quantity, the run directories it was computed from together with
the SHA-256 of their MANIFEST files, so any number in the paper can be traced to raw files.
Nothing here reads a value from the manuscript.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ablation  # noqa: E402
import baselines  # noqa: E402
import behaviour  # noqa: E402
import faults  # noqa: E402
import hrc_logs as H  # noqa: E402
import timing  # noqa: E402


def protocol(root):
    out = {}
    for d in sorted(Path(root).glob("*_protocol_bench")):
        H.verify(d)
        rows = list(csv.DictReader(open(d / "protocol_client.csv")))
        import numpy as np
        for proto in sorted({r["protocol"] for r in rows}):
            x = np.array([float(r["rtt_us"]) for r in rows if r["protocol"] == proto and r["ok"] == "1"]) / 1000
            out.setdefault(d.name, {})[proto] = {"n": int(len(x)), "median_ms": float(np.median(x)),
                                                 "p95_ms": float(np.percentile(x, 95)), "p99_ms": float(np.percentile(x, 99)),
                                                 "failed": sum(1 for r in rows if r["protocol"] == proto and r["ok"] != "1")}
    return out or None


def conformance(root):
    out = {}
    for d in sorted(Path(root).glob("*_conformance_*")):
        H.verify(d)
        rows = list(csv.DictReader(open(d / "conformance.csv")))
        out[d.name] = {"pass": sum(r["result"] == "pass" for r in rows), "fail": sum(r["result"] == "fail" for r in rows),
                       "not_run": sum(r["result"] == "not_run" for r in rows),
                       "controller_version": json.loads((d / "manifest.json").read_text()).get("controller_version"),
                       "items": rows}
    return out or None


def cbf(root):
    out = {}
    for d in sorted(Path(root).glob("*_cbf_train")):
        H.verify(d)
        m = json.loads((d / "metrics.json").read_text())
        m.pop("curve", None)
        out[d.name] = m
    return out or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--out", default="results")
    ap.add_argument("--allow-non-rt", action="store_true")
    a = ap.parse_args()
    Path(a.out).mkdir(exist_ok=True)
    res = {"generated_utc": datetime.now(timezone.utc).isoformat(), "runs_root": a.runs}
    res["timing"] = timing.analyse(a.runs, allow_non_rt=a.allow_non_rt)
    res["ablation"] = ablation.analyse(a.runs, allow_non_rt=a.allow_non_rt)
    res["fault_injection"] = faults.analyse(a.runs, ("fault_injection",))
    res["faults_in_timing_campaign"] = faults.analyse(a.runs, ("timing_campaign",))
    res["fault_sensitivity"] = faults.analyse(a.runs, ("fault_sensitivity",))
    res["tuning_selection"] = baselines.tune(a.runs, Path(a.out) / "tuning_selection.json")
    res["baseline_comparison"] = baselines.compare(a.runs)
    # release 3.1: dispatched-command check, estimate vs ground truth, floor crossings by state
    res["behaviour"] = {exp: behaviour.analyse(a.runs, exp) for exp in
                        ("timing_campaign", "baseline_compare", "fault_injection", "fault_sensitivity", "tuning", "calibration")}
    res["calibration_rule_applied"] = (json.loads((Path(__file__).resolve().parents[1] / "cfg" / "calibration_v4.json").read_text())
                                       if (Path(__file__).resolve().parents[1] / "cfg" / "calibration_v4.json").exists() else None)
    res["protocol"] = protocol(a.runs)
    res["conformance"] = conformance(a.runs)
    res["cbf_training"] = cbf(a.runs)
    # provenance: every run directory present, with the hash of its manifest
    inv = []
    for d in sorted(Path(a.runs).iterdir()):
        if (d / "MANIFEST.sha256").exists():
            inv.append({"run": d.name, "MANIFEST.sha256": hashlib.sha256((d / "MANIFEST.sha256").read_bytes()).hexdigest()})
    res["inventory"] = inv
    (Path(a.out) / "results.json").write_text(json.dumps(res, indent=2, default=str))
    print(f"wrote {Path(a.out) / 'results.json'} from {len(inv)} run directories")


if __name__ == "__main__":
    main()
