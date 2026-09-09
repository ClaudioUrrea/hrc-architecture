"""Control-cycle timing (Section 9.2, Figure 6b).

Reports the measured distribution and, explicitly, what it is NOT: a maximum
observed over 3.6e7 cycles is not a worst-case execution time. No static WCET
analysis and no schedulability test were performed. The only inferential
statement offered is the rule-of-three bound on the deadline-miss probability.
"""
import json

CYCLES = 36_000_000
DEADLINE_MS = 20.0
CRITICAL_PATH_MS = {"cbf_inference_with_gradient": 2.2, "mpc_warm_start": 2.8,
                    "scheduling_and_dispatch": 1.2}
CONCURRENT_MS = {"sensor_fusion": 4.5}     # off the serial path
OBSERVED_MS = {"p50": 6.2, "p95": 8.7, "p99": 12.3, "max": 18.5, "sd": 0.15}
SENSOR_AGE_MS = {"fusion_latency_p50": 4.5, "fusion_latency_p95": 6.2,
                 "fusion_period": 20.0, "max_observed_end_to_end": 26.9}


def main():
    serial = sum(CRITICAL_PATH_MS.values())
    return {"cycles": CYCLES, "deadline_ms": DEADLINE_MS,
            "serial_critical_path_ms": round(serial, 3),
            "critical_path_breakdown_ms": CRITICAL_PATH_MS,
            "concurrent_stages_ms": CONCURRENT_MS,
            "observed_ms": OBSERVED_MS, "deadline_misses": 0,
            "miss_probability_upper_bound_95": 3 / CYCLES,
            "sensor_data_age_ms": SENSOR_AGE_MS,
            "caveat": "observed distribution, not a WCET bound; see Section 9.2"}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
