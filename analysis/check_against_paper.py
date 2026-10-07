"""Assert that recomputed values match the values printed in the paper.

Exits non-zero on the first disagreement. Tolerances are the rounding used in
the manuscript, not free parameters.

v2.1.0. The checker now covers the quantities this round corrected,
and it carries four NEGATIVE checks - assertions that a withdrawn claim stays
withdrawn. A checker that only confirms favourable numbers is not a check.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import paper_targets as T   # the table of printed numbers; the analysis scripts never import it

EXPECTED = [
    # --- timing and the execution path -------------------------------------
    ("timing.serial_critical_path_ms", 6.2, 0.01),
    ("timing.observed_ms.execution_time_sd", 1.71, 0.01),
    ("timing.observed_ms.release_interval_sd", 0.15, 0.01),
    ("timing.block_miss_probability_upper_bound_95", 2.5e-2, 1e-6),
    ("boundaries.critical_path_ms", 6.2, 0.01),
    ("boundaries.serial_stages_ms.barrier_evaluation_as_charged_to_host", 2.49, 0.01),
    # --- commissioning and effort ------------------------------------------
    ("plc_time.mean.modular_h_measured", 3.67, 0.01),
    ("plc_time.mean.bespoke_h_estimate_lo", 40.0, 0.0),
    ("plc_time.mean.bespoke_h_estimate_hi", 45.0, 0.0),
    ("plc_time.mean.ratio_lo", 10.9, 0.05),
    ("plc_time.mean.ratio_hi", 12.3, 0.05),
    # --- faults and availability -------------------------------------------
    ("faults.events_total", 166, 0),
    ("faults.service_affecting", 156, 0),
    ("faults.operator_intervention", 6, 0),
    ("faults.automatically_recovered", 150, 0),
    ("faults.downtime_min", 180.4, 0.1),
    ("faults.availability", 0.9850, 0.0001),
    ("faults.availability_injection_cross_check", 0.9851, 0.0001),
    ("faults.availability_sensitivity.fault_rates_minus_50pct", 0.9925, 0.0001),
    ("faults.availability_sensitivity.fault_rates_plus_50pct", 0.9775, 0.0001),
    ("faults.availability_sensitivity.operator_time_15_min", 0.9917, 0.0001),
    ("faults.availability_sensitivity.operator_time_45_min", 0.9767, 0.0001),
    # --- reliability --------------------------------------------------------
    ("reliability.populations.all_faults.mtbf_h", 1.20, 0.01),
    ("reliability.populations.service_affecting.mtbf_h", 1.28, 0.01),
    ("reliability.populations.operator_intervention.mtbf_h", 33.33, 0.01),
    ("reliability.weibull.shape", 1.02, 0.01),
    ("reliability.weibull.scale_h", 1.27, 0.01),
    ("reliability.weibull.censoring.n_complete", 155, 0),
    ("reliability.weibull.censoring.n_censored", 1, 0),
    ("reliability.weibull.sensitivity_censored_point_dropped.shape", 1.016, 0.005),
    ("reliability.weibull.sensitivity_censored_point_dropped.scale_h", 1.262, 0.005),
    ("reliability.weibull.ks_p", 0.59, 0.02),
    # --- safety distance ----------------------------------------------------
    ("safety_distance.S_p_m", 1.070, 0.002),
    ("safety_distance.S_p_without_age_term_m", 1.019, 0.002),
    ("safety_distance.contribution_of_data_age_mm", 51.1, 0.5),
    # --- ablation -----------------------------------------------------------
    ("ablation.median_cost_of_architecture_ms", 0.3, 0.01),
    ("ablation.design.configurations", 7, 0),
    ("ablation.design.cells_per_configuration", 30, 0),
    ("ablation.timing_ms.A3_proposed.sd_ms", 1.71, 0.01),
    ("ablation.timing_ms.A3_proposed.jitter_ms", 0.15, 0.01),
    ("ablation.timing_ms.A0_monolithic.max", 17.9, 0.05),
    ("ablation.timing_ms.A3_proposed.max", 18.5, 0.05),
]

# v2.1.0: checks that exist because the numbers are now RECOMPUTED from data/*.parquet.
# They prove that the pipeline reproduces the printed numbers from the deposited data,
# which for reconstructed data is a statement about internal consistency only
# only.
C_ = T.CYCLES
EXPECTED += [
    ("timing.cycles", C_["n_cycles"], 0),
    ("timing.observed_ms.p50", C_["p50"], 0.01), ("timing.observed_ms.p95", C_["p95"], 0.01),
    ("timing.observed_ms.p99", C_["p99"], 0.01), ("timing.observed_ms.max", C_["max"], 0.01),
    ("timing.sensor_age_ms.fusion_latency_p50", C_["fusion"]["p50"], 0.05),
    ("timing.sensor_age_ms.fusion_latency_p95", C_["fusion"]["p95"], 0.05),
    ("timing.sensor_age_ms.max_observed_end_to_end", C_["fusion"]["max_age_ms"], 0.01),
    ("timing.deadline_misses", 0, 0),
    ("timing.independent_blocks", C_["blocks"], 0), ("timing.blocks_with_a_miss", 0, 0),
    ("timing.fallback_chain.qp_retry_events", C_["qp_retry_events"], 0),
    ("timing.fallback_chain.qp_retry_median_ms", C_["qp_retry_median_ms"], 0.05),
    ("timing.fallback_chain.qp_retry_max_ms", C_["qp_retry_max_ms"], 0.05),
    ("timing.fallback_chain.geometric_fallback_cycles", C_["geometric_fallback_cycles"], 0),
    ("boundaries.boundaries.barrier_inference.ms", C_["forward_pass_bench"]["p50"], 0.01),
    ("boundaries.boundaries.barrier_inference.max_ms", C_["forward_pass_bench"]["max"], 0.01),
    ("boundaries.boundaries.inference_with_gradient.ms", C_["with_gradient_median"], 0.01),
    ("boundaries.boundaries.qp_solve.cold_start_ms", C_["qp_cold_start_median"], 0.01),
    ("boundaries.serial_stages_ms.quadratic_programming", 2.80, 0.01),
    ("boundaries.serial_stages_ms.scheduling_serialization_dispatch", 0.91, 0.01),
    ("protocol.rows", sum(T.PROTOCOL_ROWS[k] * (5 if k in ("opcua", "modbus") else 1) for k in T.PROTOCOL_ROWS), 0),
    ("protocol.load_rpm.mean", T.LOAD_RPM["mean"], 0.5), ("protocol.load_rpm.peak", T.LOAD_RPM["peak"], 0),
    ("protocol.ethercat.slaves", T.ETHERCAT["nodes"], 0),
    ("protocol.ethercat.sdo_config_ms", T.ETHERCAT["sdo_median_ms"], 0.05),
    ("paired_stats.n_pairs", 30, 0),
    ("paired_stats.proposed.cycle.mean", T.PROPOSED["cycle"][0], 0.05),
    ("paired_stats.proposed.cycle.sd", T.PROPOSED["cycle"][1], 0.05),
    ("paired_stats.proposed.margin.mean", T.PROPOSED["margin"][0], 0.5),
    ("paired_stats.proposed.margin.sd", T.PROPOSED["margin"][1], 0.5),
    ("paired_stats.conservatism_pct.learned.mean", T.CONSERVATISM["learned"][0], 0.05),
    ("paired_stats.conservatism_pct.geometric.mean", T.CONSERVATISM["geometric"][0], 0.05),
    ("cbf_train.holdout_n", T.CBF["n"] - T.CBF["train"], 0),
    ("cbf_train.false_negatives", T.CBF["holdout_fn"], 0), ("cbf_train.false_positives", T.CBF["holdout_fp"], 0),
    ("cbf_train.accuracy", 0.972, 0.0005), ("cbf_train.false_negative_rate", 0.011, 0.0005),
    ("cbf_train.false_positive_rate", 0.045, 0.0005),
    ("cbf_train.gray_zone_abstentions", T.CBF["gray_abstain"], 0),
    ("cbf_train.gray_zone_abstention_rate", 0.914, 0.0005),
    ("cbf_train.certified_lipschitz_upper_bound", T.CBF["lipschitz_certified"], 0.001),
    # the search is a lower bound that depends on BLAS summation order: about 5.5-6.1 across machines
    ("cbf_train.empirical_lipschitz_lower_bound", T.CBF["lipschitz_empirical"], 0.7),
]
# Table 9 and Section 8.4: per-mode detection mean, per-mode recovery median, in-run recovery means, pooled values
for m, v in T.FAULTS["detect_mean"].items():
    EXPECTED.append((f"faults.per_mode.{m}.detection_mean_ms", v, 0.5))
for m, v in T.FAULTS["recover_median"].items():
    EXPECTED.append((f"faults.per_mode.{m}.recovery_median_s", v, 0.051))
for m, v in T.FAULTS["recover_mean_in_run"].items():
    EXPECTED.append((f"faults.in_run_recovery_mean_s.{m}", v, 0.051))
EXPECTED += [
    ("faults.pooled.detection_ms.p50", T.FAULTS["detect_pooled"]["p50"], 0.5),
    ("faults.pooled.detection_ms.p95", T.FAULTS["detect_pooled"]["p95"], 0.5),
    ("faults.pooled.detection_ms.max", T.FAULTS["detect_pooled"]["max"], 0.5),
    ("faults.pooled.automatic_recovery_s.p50", 2.8, 0.051),
    ("faults.operator_intervention_mean_min", T.FAULTS["operator_mean_min"], 0.05),
    ("faults.automatic_recovery_downtime_min", 10.0, 0.05),
]
for cfg, v in T.ABLATION.items():
    for k_json, k_t, tol in (("p50", "p50", 0.051), ("p95", "p95", 0.051), ("p99", "p99", 0.051),
                             ("max", "mx", 0.051), ("sd_ms", "sd", 0.0051), ("jitter_ms", "jitter", 0.0051),
                             ("miss_pct", "miss_pct", 0.005)):
        EXPECTED.append((f"ablation.timing_ms.{cfg}.{k_json}", v[k_t], tol))
    EXPECTED.append((f"ablation.timing_ms.{cfg}.ci95.0", v["ci"][0], 0.051))
    EXPECTED.append((f"ablation.timing_ms.{cfg}.ci95.1", v["ci"][1], 0.051))
for (proto, op), (a, b, c) in T.PROTOCOL.items():
    key = {"rest": "rest_ms", "opcua": "opcua_ms_p50_p95_p99", "modbus": "modbus_ms_p50_p95_p99"}[proto]
    for i, w in enumerate((a, b, c)):
        EXPECTED.append(("protocol." + key + (f".{['p50', 'p95', 'p99'][i]}" if proto == "rest" else f".{op}.{i}"), w, 0.051))
for ep, table in (("cycle", T.TUNED_CYCLE), ("margin", T.TUNED_MARGIN)):
    for b, (m, sd, dz, p_raw, p_holm) in table.items():
        sel = f"paired_stats.tuned[baseline={b},endpoint={ep}]"
        EXPECTED.append((sel + ".baseline_mean", m, 0.05 if ep == "cycle" else 0.5))
        EXPECTED.append((sel + ".d_z", dz, 0.006 if dz < 1 else 0.01))
        if p_holm is not None:
            EXPECTED.append((sel + ".p_holm", p_holm, 0.0006 if p_holm < 0.01 else 0.0051))
        if p_raw is not None:
            EXPECTED.append((sel + ".p_raw", p_raw, 0.0006 if p_raw < 0.01 else 0.006))
        EXPECTED.append((sel + ".baseline_sd", sd, 0.05 if ep == "cycle" else 0.5))
        lo, hi = T.TUNED_CI[(ep, b)]
        EXPECTED.append((sel + ".ci95_bca.0", lo, 0.06 if ep == "cycle" else 0.6))
        EXPECTED.append((sel + ".ci95_bca.1", hi, 0.06 if ep == "cycle" else 0.6))
for b, (m, sd, dsd) in T.UNTUNED_CYCLE.items():
    EXPECTED.append((f"paired_stats.untuned[baseline={b},endpoint=cycle].baseline_mean", m, 0.05))

# Documented departures between the manuscript and what the data can support. They are reported,
# not asserted: a number that cannot be reproduced must be visible, not silently loosened.
KNOWN_DEVIATIONS = []     # v2.1.0: the two v2.1.0-draft departures (Lipschitz 8.7, SVO-CBF SD 2.3) were corrected in the manuscript

# Claims this round withdrew. Each must stay withdrawn: the pipeline fails if a
# later edit quietly reinstates one.
WITHDRAWN = [
    ("timing.per_cycle_bound_withdrawn", True,
     "the per-cycle rule-of-three deadline-miss bound"),
    ("ablation.architecture_improves_tail_vs_monolith", False,
     "the claim that the layering improves the latency tail"),
    ("tune_baselines.effect_on_the_papers_claims.DMPC.significant_after_tuning", False,
     "a significant cycle-time advantage over tuned DMPC"),
    ("tune_baselines.effect_on_the_papers_claims.SVO-CBF.significant_after_tuning", False,
     "a significant cycle-time advantage over tuned SVO-CBF"),
]

# Identity checks: values that must match a string, not a number.
IDENTITIES = [
    ("ablation.configuration_with_lowest_max", "A0_monolithic",
     "the monolith, not the proposal, holds the lowest observed maximum"),
    ("faults.source_of_recovery_times",
     "the 200 h run only; the injection campaign is a cross-check, not an input",
     "availability must not borrow the injection campaign's recovery mean"),
]


def dig(d, path):
    for part in path.split("."):
        if "[" in part:                       # name[key=value,key=value] selects a row of a list
            name, sel = part[:-1].split("[")
            want = dict(kv.split("=") for kv in sel.split(","))
            d = next(r for r in d[name] if all(str(r[k]) == v for k, v in want.items()))
        elif isinstance(d, list):
            d = d[int(part)]
        else:
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

    for key, want, what in WITHDRAWN:
        got = dig(results, key)
        ok = got is want
        print(f"{'OK  ' if ok else 'FAIL'}  [withdrawn] {what}: flag is {got}, "
              f"must be {want}")
        bad += not ok

    for key, want, why in IDENTITIES:
        got = dig(results, key)
        ok = got == want
        print(f"{'OK  ' if ok else 'FAIL'}  [identity] {key}: {why}")
        bad += not ok

    for key, printed, why in KNOWN_DEVIATIONS:
        print(f"NOTE  [known deviation] {key}: data give {dig(results, key)}, paper prints {printed}. {why}")

    if bad:
        sys.exit(f"{bad} value(s) disagree with the manuscript")
    print(f"all {len(EXPECTED) + len(WITHDRAWN) + len(IDENTITIES)} checked values "
          f"agree with the manuscript")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="out/results.json")
    main(ap.parse_args().results)
