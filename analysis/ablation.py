"""Architectural ablation A0-A3 (Section 9.6, Table 11, Figure 11).

v2.0.0 (round 2). Three things changed, each because a reviewer was right.

1. SEVEN configurations, not four. A2 of the first version removed real-time
   priority, core isolation and the watchdog together, so it could not say which
   of the three mattered. It is now decomposed into A2a, A2b and A2c, with A2
   retained as the all-three-removed case.

2. THIRTY condition cells per configuration, not one replayed workload:
   5 human-trajectory seeds x 3 scenarios x 2 background loads. The figures
   below are pooled over the 30 cells of each configuration.

3. The dispersion column is SPLIT. The first version printed, for A3, a median
   of 6.2 ms, a 99th percentile of 12.3 ms and a standard deviation of 0.15 ms.
   Those three numbers cannot describe one sample. 0.15 ms is the standard
   deviation of the RELEASE INTERVAL - the period between successive activations
   of the control thread, nominally 20 ms - which measures scheduling
   regularity, not execution-time spread. The execution-time dispersion
   recomputed from the raw logs is 1.71 ms. Both are now reported, under their
   own names, for every configuration.

The result remains deliberately unflattering, and is now less flattering than
before: the architecture does not make the loop faster (it costs ~0.3 ms of
median cycle time against the monolith) AND it does not improve the latency
tail (A0 holds the lowest maximum of the seven). What the ablation does
establish about the tail is conditional: GIVEN a layered system, the tail is set
by the transport and the scheduling discipline.

v2.1.0. Every number in the timing table is computed from
data/ablation_cycles.parquet (7 configurations x 30 cells x 10,000 cycles); the
dictionary of constants that earlier versions carried is gone. The interval on the
median is a BCa bootstrap over the 30 run-level medians (10,000 resamples, seed in
config/seeds.json). The qualitative properties at the bottom are design
properties of the configurations, not measurements, and stay as declared values.
"""
import json
import os
import sys

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hrc_stats import bca_ci   # noqa: E402

PATH = "data/ablation_cycles.parquet"
DEADLINE_MS = 20.0
SEEDS = "config/seeds.json"

LAYERED = ["A1_socket_ipc", "A2a_no_rt_priority", "A2b_shared_core", "A2c_no_watchdog",
           "A2_all_three_removed", "A3_proposed"]

# Corrected in v2.0.0. The first version claimed isolated unit testing of the
# safety module for A3 alone. That was wrong: isolated testability is a property
# of the interface contracts, which every layered configuration retains. Only
# the monolith, which calls vendor libraries from control code, lacks it.
QUALITATIVE = {
 "isolated_unit_testing_of_safety_module": {
     "A0_monolithic": "no", **{k: "yes" for k in LAYERED}},
 "builds_without_vendor_sdk_on_the_link_line": {
     "A0_monolithic": "no", **{k: "yes" for k in LAYERED}},
 "vendor_swap_without_editing_control_code": {
     "A0_monolithic": "no", **{k: "yes" for k in LAYERED}},
 "loc_touched_to_add_a_platform": {
     "A0_monolithic": "8000-10000 (estimated)", **{k: "456-523" for k in LAYERED}},
}



def _bca_seed():
    try:
        return json.load(open(SEEDS))["bootstrap"]["bca_ablation_cells"]
    except (OSError, KeyError):
        return 11072027


def main(path=PATH):
    d = pq.read_table(path).to_pandas()
    d["config"] = d["config"].astype(str)
    cells = ["seed", "scenario", "load"]
    configs = {}
    for name, g in d.groupby("config", sort=False):
        x = g["execution_ms"].to_numpy(np.float64)
        run_med = g.groupby(cells, observed=True)["execution_ms"].median().to_numpy(np.float64)
        lo, hi = bca_ci(run_med, n_boot=10_000, seed=_bca_seed())
        configs[name] = {
            "n_cycles": int(x.size), "cells": int(run_med.size),
            "p50": round(float(np.median(x)), 2),
            "ci95": [round(lo, 2), round(hi, 2)],
            "p95": round(float(np.quantile(x, 0.95)), 2),
            "p99": round(float(np.quantile(x, 0.99)), 2),
            "max": round(float(x.max()), 2),
            "sd_ms": round(float(x.std(ddof=1)), 3),                                   # execution time
            "jitter_ms": round(float(g["release_interval_ms"].astype(np.float64).std(ddof=1)), 3),  # release interval
            "miss_pct": round(100.0 * float((x > DEADLINE_MS).mean()), 3)}
    configs = {k: configs[k] for k in sorted(configs, key=lambda s: ["A0", "A1", "A2a", "A2b", "A2c", "A2_", "A3"].index(
        next(p for p in ["A0", "A1", "A2a", "A2b", "A2c", "A2_", "A3"] if s.startswith(p))))}
    cost = configs["A3_proposed"]["p50"] - configs["A0_monolithic"]["p50"]
    lowest_max = min(configs, key=lambda k: configs[k]["max"])
    no_miss = {k: ("yes" if v["miss_pct"] == 0.0 else "no") for k, v in configs.items()}
    qual = dict(QUALITATIVE)
    qual["no_deadline_miss_over_the_campaign"] = no_miss
    return {
        "source": path,
        "design": {"configurations": len(configs),
                   "seeds": int(d["seed"].nunique()), "scenarios": int(d["scenario"].nunique()),
                   "background_loads": int(d["load"].nunique()),
                   "cells_per_configuration": int(d.groupby(cells, observed=True).ngroups),
                   "cycles_per_cell": int(d.groupby(["config"] + cells, observed=True).size().iloc[0])},
        "timing_ms": configs,
        "median_cost_of_architecture_ms": round(cost, 2),
        "median_cost_pct": round(100 * cost / configs["A0_monolithic"]["p50"], 1),
        # Reported explicitly so the checker can assert that the withdrawn tail
        # claim stays withdrawn: the monolith, not the proposal, holds the
        # lowest maximum.
        "configuration_with_lowest_max": lowest_max,
        "architecture_improves_tail_vs_monolith":
            bool(configs["A3_proposed"]["max"] < configs["A0_monolithic"]["max"]),
        "properties_not_captured_by_timing": qual,
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
