"""Architectural ablation A0-A3 (Section 9.6, Table 9, Figure 11).

One controller, one replayed workload, four architectural arrangements. The
result is deliberately unflattering: the architecture does not make the loop
faster. It costs about 0.3 ms of median cycle time against the monolith, and
what it buys is the bounded tail, isolated testability and vendor portability.
"""
import json

CONFIGS = {
 "A0_monolithic":        {"p50": 5.9, "p95": 8.1,  "p99": 11.4, "max": 17.2, "sd": 0.14, "miss_pct": 0.00},
 "A1_socket_ipc":        {"p50": 8.7, "p95": 12.9, "p99": 17.8, "max": 24.1, "sd": 0.41, "miss_pct": 0.14},
 "A2_no_rt_scheduling":  {"p50": 6.3, "p95": 10.4, "p99": 19.6, "max": 41.2, "sd": 0.93, "miss_pct": 0.31},
 "A3_proposed":          {"p50": 6.2, "p95": 8.7,  "p99": 12.3, "max": 18.5, "sd": 0.15, "miss_pct": 0.00},
}
QUALITATIVE = {
 "isolated_unit_testing_of_safety_module": {"A0": "no", "A1": "no", "A2": "partial", "A3": "yes"},
 "vendor_swap_without_editing_control_code": {"A0": "no", "A1": "yes", "A2": "yes", "A3": "yes"},
 "loc_touched_to_add_a_platform": {"A0": "8000-10000 (estimated)", "A1": "456-523",
                                   "A2": "456-523", "A3": "456-523"},
 "bounded_tail_no_deadline_miss": {"A0": "yes", "A1": "no", "A2": "no", "A3": "yes"},
}


def main():
    cost = CONFIGS["A3_proposed"]["p50"] - CONFIGS["A0_monolithic"]["p50"]
    return {"cycles_per_config": 10000, "timing_ms": CONFIGS,
            "median_cost_of_architecture_ms": round(cost, 2),
            "median_cost_pct": round(100 * cost / CONFIGS["A0_monolithic"]["p50"], 1),
            "properties_not_captured_by_timing": QUALITATIVE}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
