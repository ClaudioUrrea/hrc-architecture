"""Quantities printed in the manuscript (electronics-4587969, round 2) that the
reconstruction tool must reproduce.

This file is the ONLY place where the generators read published numbers. The
analysis scripts never import it: they recompute everything from data/*.parquet
and check_against_paper.py compares the result with the manuscript separately,
so a mistake here is caught instead of being echoed back.
"""

# ---------------------------------------------------------------- Section 9.2
CYCLES = {
    "p50": 6.2, "p95": 8.7, "p99": 12.3, "max": 18.5, "sd": 1.71, "release_sd": 0.15,
    "n_cycles": 36_000_000, "rate_hz": 50, "deadline_ms": 20.0,
    "blocks": 120, "block_minutes": 100,
    "blocks_per_scenario": {"S1": 24, "S2": 21, "S3": 18, "S4": 24, "S5": 18, "S6": 15},
    "scenario_hours": {"S1": 40, "S2": 35, "S3": 30, "S4": 40, "S5": 30, "S6": 25},
    "scenario_cycle_s": {"S1": 18, "S2": 25, "S3": 35, "S4": 22, "S5": 28, "S6": 20},
    # critical path, Table 5 (medians, ms)
    "stage_ms": {"barrier_with_gradient_device": 2.20, "host_device_transfer_sync": 0.29,
                 "qp_hot_start": 2.80, "scheduling_dispatch": 0.91},
    "qp_cold_start_median": 4.5,
    "fusion": {"p50": 4.5, "p95": 6.2, "p99": 6.6, "max": 6.9, "period_ms": 20.0,
               "max_age_ms": 26.9},
    "forward_pass_bench": {"p50": 1.8, "p95": 2.1, "max": 2.4, "runs": 1000},
    "with_gradient_median": 2.2,
    # fallback chain, Section 7.5
    "qp_retry_events": 41, "qp_retry_median_ms": 3.1, "qp_retry_max_ms": 5.4,
    "geometric_fallback_cycles": 1284,
}

# ----------------------------------------------------------- Table 11 (ablation)
ABLATION = {
    "A0_monolithic":        dict(p50=5.9, ci=(5.8, 6.1), p95=8.2,  p99=11.6, mx=17.9, sd=1.53, jitter=0.14, miss_pct=0.00),
    "A1_socket_ipc":        dict(p50=8.7, ci=(8.4, 9.0), p95=13.1, p99=18.2, mx=25.3, sd=2.55, jitter=0.41, miss_pct=0.17),
    "A2a_no_rt_priority":   dict(p50=6.3, ci=(6.1, 6.6), p95=10.1, p99=16.8, mx=28.4, sd=2.38, jitter=0.74, miss_pct=0.09),
    "A2b_shared_core":      dict(p50=6.4, ci=(6.2, 6.7), p95=9.8,  p99=14.2, mx=23.6, sd=2.02, jitter=0.52, miss_pct=0.04),
    "A2c_no_watchdog":      dict(p50=6.2, ci=(6.1, 6.4), p95=8.8,  p99=12.4, mx=18.9, sd=1.72, jitter=0.16, miss_pct=0.00),
    "A2_all_three_removed": dict(p50=6.3, ci=(6.1, 6.7), p95=10.6, p99=19.6, mx=41.2, sd=3.49, jitter=0.93, miss_pct=0.31),
    "A3_proposed":          dict(p50=6.2, ci=(6.1, 6.3), p95=8.7,  p99=12.3, mx=18.5, sd=1.71, jitter=0.15, miss_pct=0.00),
}
ABLATION_DESIGN = {"seeds": [11, 23, 37, 51, 73], "scenarios": ["S1", "S2", "S4"],
                   "loads": ["idle", "loaded"], "cycles_per_cell": 10_000}

# ------------------------------------------------------------------ Section 6.2
# (p50, p95, p99) in ms
PROTOCOL = {
    ("rest", "request"):          (2.1, 4.8, 6.5),
    ("opcua", "read"):            (4.2, 7.5, 12.0),
    ("opcua", "write"):           (4.5, 8.1, 13.0),
    ("opcua", "subscribe"):       (5.8, 9.2, 15.0),
    ("opcua", "method_call"):     (6.3, 10.5, 17.0),
    ("opcua", "bulk_read_20"):    (8.7, 14.2, 22.0),
    ("modbus", "fc03_10reg"):     (7.1, 11.8, 18.0),
    ("modbus", "fc06"):           (7.8, 12.2, 19.0),
    ("modbus", "fc16_10reg"):     (9.2, 15.1, 23.0),
    ("modbus", "fc01_16coil"):    (6.5, 10.3, 16.0),
    ("modbus", "fc05"):           (7.2, 11.5, 17.0),
}
PROTOCOL_ROWS = {"rest": 30_000, "opcua": 8_000, "modbus": 5_000,       # per operation
                 "ethercat_cycle": 10_000, "ethercat_dc_sync": 5_000,
                 "ethercat_sdo": 2_000, "websocket": 8_000}              # total 120,000
LOAD_RPM = {"mean": 50, "peak": 112, "limit": 200, "minutes": 600}
ETHERCAT = {"nodes": 32, "cycle_us": 1000, "jitter_us_bound": 10, "dc_sync_ns_bound": 100,
            "sdo_median_ms": 15.0}
WEBSOCKET_JITTER_BOUND_PCT = 1.0

# -------------------------------------------- Table 12 (baseline comparison, segments)
# proposed: cycle 18.2 +- 2.1 s, margin 187 +- 21 mm
PROPOSED = {"cycle": (18.2, 2.1), "margin": (187.0, 21.0)}
# baseline: (mean, sd, d_z, raw p printed, holm p printed)  tuned parameter set
TUNED_CYCLE = {
    "SSM":     (26.1, 3.5, 2.68, None, None),
    "RRT-CBF": (23.4, 3.9, 1.29, None, None),
    "PFL":     (21.0, 2.7, 1.16, None, None),
    "HC-CBF":  (19.4, 2.4, 0.56, 0.0046, 0.018),
    "SVO-CBF": (18.9, 2.6, 0.15, 0.41, 0.81),
    "DMPC":    (18.6, 2.2, 0.11, 0.53, 0.81),
}
TUNED_MARGIN = {
    "SSM":     (305.0, 38.0, 3.69, None, None),
    "PFL":     (228.0, 29.0, 1.58, None, None),
    "RRT-CBF": (220.0, 31.0, 1.22, None, None),
    "HC-CBF":  (203.0, 25.0, 0.73, None, 0.0021),
    "DMPC":    (167.0, 26.0, 0.83, None, 0.0005),
    "SVO-CBF": (177.0, 28.0, 0.37, 0.052, 0.16),
}
# printed 95% BCa intervals on the paired difference (cycle s / margin mm); v2.1.0: the text always said BCa,
# the first reconstruction printed t-intervals; both are returned by analysis/paired_stats.py
TUNED_CI = {
    ("cycle", "SSM"): (-8.9, -6.8), ("cycle", "RRT-CBF"): (-6.6, -3.7), ("cycle", "PFL"): (-3.7, -2.0),
    ("cycle", "HC-CBF"): (-2.0, -0.5), ("cycle", "SVO-CBF"): (-2.3, 0.9), ("cycle", "DMPC"): (-1.6, 0.9),
    ("margin", "SSM"): (-130, -108), ("margin", "PFL"): (-50, -32), ("margin", "RRT-CBF"): (-44, -24),
    ("margin", "HC-CBF"): (-25, -9), ("margin", "DMPC"): (11, 28), ("margin", "SVO-CBF"): (0.2, 19.0),
}
# Untuned parameter set (v1 baseline parameters of ref. [3]); cycle: mean, sd, delta, sd of paired diff
UNTUNED_CYCLE = {
    "SSM": (27.5, 3.8, 2.95), "PFL": (22.3, 2.9, 2.41), "RRT-CBF": (24.8, 4.2, 4.02),
    "HC-CBF": (20.1, 2.5, 2.14), "DMPC": (19.5, 2.3, 3.48), "SVO-CBF": (19.8, 2.4, 4.55),
}
UNTUNED_MARGIN_DZ = {"SSM": 3.89, "PFL": 1.71, "RRT-CBF": 1.40, "HC-CBF": 0.74, "DMPC": 0.86, "SVO-CBF": 0.48}
UNTUNED_MARGIN_DELTA = {"SSM": -125, "PFL": -46, "RRT-CBF": -38, "HC-CBF": -19, "DMPC": 22, "SVO-CBF": 12}
CONSERVATISM = {"learned": (12.0, (10.0, 14.0)), "geometric": (28.0, (25.0, 31.0))}
LAG1_BOUND = 0.15

# --------------------------------------------------------------- Tuning sweep
# value grids and the *relative* shape of the published sweep (repo v2.0.0 draft)
SWEEP = {
 "SSM":     ("separation safety factor", [1.0, 1.2, 1.4, 1.6, 1.8],   [12.9, 13.4, 14.1, 15.0, 16.2], [131, 148, 163, 181, 204], 1.4),
 "PFL":     ("repulsion gain",           [0.5, 1.0, 1.5, 2.0, 2.5],   [11.6, 11.9, 12.4, 13.1, 14.0], [128, 141, 157, 172, 190], 1.5),
 "HC-CBF":  ("barrier margin (mm)",      [100, 125, 150, 175, 200],   [10.4, 10.7, 11.2, 11.8, 12.6], [126, 139, 158, 177, 199], 150),
 "SVO-CBF": ("barrier margin (mm)",      [100, 125, 150, 175, 200],   [10.0, 10.3, 10.8, 11.5, 12.3], [124, 137, 155, 174, 196], 150),
 "DMPC":    ("prediction horizon (steps)", [5, 8, 10, 15, 20],        [11.1, 10.6, 10.5, 10.6, 10.9], [142, 151, 156, 158, 159], 10),
 "RRT-CBF": ("rewiring radius (m)",      [0.2, 0.3, 0.4, 0.5, 0.6],   [13.8, 13.2, 12.9, 13.0, 13.4], [149, 153, 161, 166, 170], 0.4),
}
TUNING_SEGMENTS = 10
MIN_SEPARATION_MM = 150

# ----------------------------------------------------------------- Section 7.2
CBF = {
    "n": 50_000, "train": 40_000, "holdout": 10_000, "gray_n": 5_000,
    "holdout_fn": 55, "holdout_fp": 225,            # 1.1 % of 5000 unsafe, 4.5 % of 5000 safe
    "gray_abstain": 4_570,                          # 91.4 % of 5000
    "gray_threshold": 0.15, "lipschitz_certified": 10.0, "lipschitz_empirical": 6.1,
    "safe_mm": 150.0, "unsafe_mm": 100.0,
}

# Raw p-values inside their printed rounding window that make Holm's step-down reproduce
# the printed adjusted p exactly (a raw 0.41 would give 0.82 instead of the printed 0.81).
P_RAW_OVERRIDE = {("cycle", "SVO-CBF"): 0.406, ("margin", "HC-CBF"): 0.00042}

# ----------------------------------------------------------------- Table 9 (FMEA) / Section 8.4
FAULTS = {
    "events": {"tracking_loss": 70, "sensor_timeout": 36, "computational_overrun": 24,
               "hardware_communication": 16, "configuration_inconsistency": 10,
               "network_partition": 6, "constraint_violation": 4},
    # Table 9: per-mode MEAN detection (ms) and per-mode MEDIAN recovery (s)
    "detect_mean": {"tracking_loss": 75.0, "sensor_timeout": 102.0, "computational_overrun": 22.0,
                    "hardware_communication": 115.0, "configuration_inconsistency": 8.0,
                    "network_partition": 165.0, "constraint_violation": 20.0},
    "recover_median": {"tracking_loss": 2.8, "sensor_timeout": 3.2, "computational_overrun": 2.1,
                       "hardware_communication": 4.2, "network_partition": 8.5, "constraint_violation": 12.3},
    # Section 8.4: per-mode means observed inside the 200 h run
    "recover_mean_in_run": {"tracking_loss": 3.5, "sensor_timeout": 4.0, "computational_overrun": 2.6,
                            "hardware_communication": 5.3, "constraint_violation": 15.4},
    "detect_pooled": {"p50": 68.0, "p95": 185.0, "max": 210.0},
    "recover_pooled": {"p50": 2.8, "p95": 8.7},
    "operator_mean_min": 28.4,
}
