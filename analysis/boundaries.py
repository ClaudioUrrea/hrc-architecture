"""Timing boundaries (Section 3.4, Table 5, Figure A1), recomputed from data/stage_timings.parquet.

A reviewer asked where each stage runs, how the two devices communicate, and
exactly which transfers are inside the 6.2 ms figure. The previous version did
not say, and the arithmetic did not visibly close: 2.2 ms of inference plus
2.8 ms of QP plus "scheduling and dispatch" was quoted as 6.2 ms without the
transfer being named anywhere.

It closes here. Every reported figure is defined by the instant at which
measurement starts, the instant at which it stops, and the device on which the
work runs - that part is descriptive and lives in BOUNDARIES. The numbers are
medians of the stage durations in data/stage_timings.parquet (1,000 cycles
chosen at equally spaced ranks of the cycle time, so that the sample reproduces
the quantiles of the whole campaign, plus two 1,000-run micro-benchmarks of the
barrier network). The assertions fail the build if the itemized stages stop
summing to the critical path.
"""
import json
import numpy as np
import pyarrow.parquet as pq

DEADLINE_MS = 20.0
PATH = "data/stage_timings.parquet"
TOL = 0.011          # ms: manuscript prints two decimals

BOUNDARIES = {
 "critical_path": {
    "device": "host + Jetson",
    "starts": "dequeue of the state event from the shared-memory ring",
    "stops": "write of the command into the outbound ring",
    "includes": ["inference request", "host-to-device transfer",
                 "device-to-host transfer", "stream synchronization",
                 "QP solve", "bookkeeping"],
    "excludes": ["simulator physics", "protocol service", "command transmission"]},
 "barrier_inference": {
    "device": "Jetson",
    "starts": "first TensorRT kernel launch", "stops": "completion of the last kernel",
    "excludes": ["transfer", "synchronization"]},
 "inference_with_gradient": {
    "device": "Jetson",
    "starts": "first TensorRT kernel launch",
    "stops": "completion of the automatic-differentiation pass",
    "excludes": ["transfer", "synchronization"]},
 "host_device_round_trip": {
    "device": "link",
    "starts": "enqueue of the transfer", "stops": "return of the synchronization call",
    "includes": ["pinned-memory transfer both ways", "one stream synchronization"],
    "note": "the difference between the device computation and the figure charged "
            "to the critical path"},
 "qp_solve": {
    "device": "host",
    "starts": "entry to qpOASES::hotstart", "stops": "return",
    "note": "warm start; cold start is reported separately"},
 "sensor_fusion": {
    "device": "host",
    "starts": "arrival of the last contributing frame",
    "stops": "publication into the lock-free slot",
    "note": "concurrent thread, NOT on the critical path, but enters the "
            "data-age budget of Section 9.2"},
 "protocol_transactions": {
    "device": "host",
    "starts": "request received at the server socket",
    "stops": "reply handed to the socket",
    "excludes": ["client-side processing in the PLC simulator"]},
}


def main(path=PATH):
    d = pq.read_table(path).to_pandas()
    med = d.groupby("stage")["duration_ms"].median()
    q = lambda s, p: float(d.loc[d["stage"] == s, "duration_ms"].quantile(p))
    crit = d[d["on_critical_path"]]
    per_cycle = crit.groupby("cycle_index")["duration_ms"].sum()
    critical_path = float(per_cycle.median())
    gradient = float(med["barrier_inference_with_gradient"])
    transfer = float(med["host_device_transfer_sync"])
    serial = {
        "barrier_evaluation_as_charged_to_host": round(gradient + transfer, 3),   # device + transfer
        "quadratic_programming": round(float(med["qp_solve_hotstart"]), 3),
        "scheduling_serialization_dispatch": round(float(med["scheduling_serialization_dispatch"]), 3)}
    total = round(sum(serial.values()), 3)
    assert abs(total - round(critical_path, 3)) < TOL, (
        f"itemized stages sum to {total} ms, per-cycle critical path median is {critical_path:.3f} ms")
    fwd = d.loc[d["stage"] == "bench_forward_pass", "duration_ms"]
    b = {k: dict(v) for k, v in BOUNDARIES.items()}
    b["critical_path"]["ms"] = round(critical_path, 3)
    b["barrier_inference"]["ms"] = round(float(fwd.median()), 3)
    b["barrier_inference"]["p95_ms"] = round(float(fwd.quantile(.95)), 3)
    b["barrier_inference"]["max_ms"] = round(float(fwd.max()), 3)
    b["barrier_inference"]["runs"] = int(fwd.size)
    b["inference_with_gradient"]["ms"] = round(float(med["bench_forward_plus_gradient"]), 3)
    b["inference_with_gradient"]["campaign_median_ms"] = round(gradient, 3)
    b["host_device_round_trip"]["ms"] = round(transfer, 3)
    b["qp_solve"]["ms"] = serial["quadratic_programming"]
    b["qp_solve"]["cold_start_ms"] = round(float(med["bench_qp_coldstart"]), 3)
    b["sensor_fusion"]["ms"] = round(float(med["sensor_fusion"]), 3)
    return {"deadline_ms": DEADLINE_MS, "source": path,
            "instrumented_cycles": int(per_cycle.size),
            "serial_stages_ms": serial,
            "critical_path_ms": total,
            "critical_path_median_of_per_cycle_sums_ms": round(critical_path, 3),
            "boundaries": b,
            "devices": {"host": "x86-64 workstation, PREEMPT_RT kernel",
                        "jetson": "NVIDIA Jetson Xavier NX, TensorRT FP16",
                        "link": "dedicated gigabit link, pinned memory (Figure A1)"}}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
