"""Control-cycle timing (Section 9.2, Figure 6b), recomputed from data/cycles_36M.parquet.

Reports the measured distribution and, explicitly, what it is NOT: a maximum
observed over 3.6e7 cycles is not a worst-case execution time. No static WCET
analysis and no schedulability test were performed.

v2.0.0 (round 2). TWO CORRECTIONS.

1. THE PER-CYCLE RULE-OF-THREE BOUND IS WITHDRAWN. v1.0.0 applied the rule of
   three to 3.6e7 cycles treated as independent trials, giving 8.3e-8, while
   Section 9.7 of the same paper argues that consecutive cycles are strongly
   dependent. A reviewer flagged the contradiction. Independence does not hold
   at the cycle grain, so the bound was not computed on a valid sample.

   What the design does supply is independence at a coarser grain: 120 blocks of
   100 minutes, each begun from a cold start with its own seed, scenario
   assignment and background-load schedule, with the host re-initialized between
   blocks. None of the 120 contained a deadline miss, so the rule of three
   applied AT THAT GRAIN bounds the probability that a 100-minute block contains
   at least one miss at 3/120 = 2.5e-2. That is a far weaker statement, and it is
   the statement the data support. It is deliberately NOT converted back to a
   per-cycle figure: doing so would reintroduce the assumption the block-level
   analysis exists to avoid.

2. THE DISPERSION FIELD IS SPLIT. `sd` of v1.0.0 was the standard deviation of
   the RELEASE INTERVAL (0.15 ms), not of the execution time, which cannot be
   0.15 ms for a sample with a median of 6.2 ms and a 99th percentile of
   12.3 ms. Execution-time dispersion recomputed from the raw logs is 1.71 ms.

v2.1.0. Every number below is now computed from the data file; none is a
constant. The release-interval SD comes from the A3 rows of
data/ablation_cycles.parquet because the 36M-cycle file does not record release
times. Percentiles use a 1-microsecond histogram, so they are exact for data
stored at that resolution and need no more than a few MB of memory.
"""
import json
import os
import numpy as np
import pyarrow.parquet as pq
from scipy import stats

DEADLINE_MS = 20.0
PATH = "data/cycles_36M.parquet"
ABLATION = "data/ablation_cycles.parquet"
BINS = 60_000          # 1 us bins up to 60 ms; anything above lands in the last bin


def _hist_quantile(counts, q):
    cum = np.cumsum(counts)
    return float(np.searchsorted(cum, q * cum[-1], side="left")) / 1000.0


def scan(path=PATH, batch=2_000_000):
    pf = pq.ParquetFile(path)
    cols = ["cycle_ms", "cbf_ms", "qp_ms", "dispatch_ms", "fusion_ms", "sensor_age_ms",
            "block", "deadline_miss", "fallback_step", "qp_retry_ms", "scenario"]
    hists = {c: np.zeros(BINS + 1, np.int64) for c in
             ("cycle_ms", "cbf_ms", "qp_ms", "dispatch_ms", "fusion_ms")}
    n = 0
    s1 = s2 = 0.0
    vmax = 0.0
    age_max = 0.0
    misses = 0
    block_miss = {}
    block_n = {}
    step_counts = {0: 0, 1: 0, 2: 0}
    retry = []
    for rb in pf.iter_batches(batch_size=batch, columns=cols):
        d = rb.to_pandas()
        x = d["cycle_ms"].to_numpy(np.float64)
        n += x.size
        s1 += x.sum()
        s2 += np.square(x).sum()
        vmax = max(vmax, float(x.max()))
        age_max = max(age_max, float(d["sensor_age_ms"].max()))
        miss = d["deadline_miss"].to_numpy()
        misses += int(miss.sum())
        for b, g in d.groupby("block"):
            block_n[b] = block_n.get(b, 0) + len(g)
            block_miss[b] = block_miss.get(b, 0) + int(g["deadline_miss"].sum())
        for c in hists:
            v = np.minimum(np.rint(d[c].to_numpy(np.float64) * 1000).astype(np.int64), BINS)
            hists[c] += np.bincount(np.maximum(v, 0), minlength=BINS + 1)
        for k in step_counts:
            step_counts[k] += int((d["fallback_step"] == k).sum())
        r = d["qp_retry_ms"].dropna().to_numpy(np.float64)
        if r.size:
            retry.append(r)
    mean = s1 / n
    sd = float(np.sqrt((s2 / n - mean * mean) * n / (n - 1)))
    return dict(n=n, mean=mean, sd=sd, max=vmax, age_max=age_max, misses=misses, hists=hists,
                block_miss=block_miss, block_n=block_n, steps=step_counts,
                retry=np.concatenate(retry) if retry else np.array([]))


def release_interval_sd(path=ABLATION, config="A3_proposed"):
    t = pq.read_table(path, columns=["config", "release_interval_ms"]).to_pandas()
    return float(t.loc[t["config"] == config, "release_interval_ms"].astype(float).std(ddof=1))


def main(path=PATH):
    r = scan(path)
    H = r["hists"]
    q = lambda c, p: _hist_quantile(H[c], p)
    blocks = len(r["block_n"])
    blocks_with_miss = sum(1 for v in r["block_miss"].values() if v > 0)
    if blocks_with_miss == 0:
        upper = 3.0 / blocks                     # rule of three, at the BLOCK grain only
        method = "rule of three"
    else:                                         # exact one-sided Clopper-Pearson
        upper = float(stats.beta.ppf(0.95, blocks_with_miss + 1, blocks - blocks_with_miss))
        method = "Clopper-Pearson"
    serial = {"barrier_evaluation_as_charged_to_host": q("cbf_ms", .5),
              "quadratic_programming": q("qp_ms", .5),
              "scheduling_serialization_dispatch": q("dispatch_ms", .5)}
    rel_sd = release_interval_sd() if os.path.exists(ABLATION) else None
    ret = r["retry"]
    return {
        "cycles": r["n"], "deadline_ms": DEADLINE_MS, "source": path,
        "serial_critical_path_ms": round(sum(serial.values()), 3),
        "critical_path_breakdown_ms": {k: round(v, 3) for k, v in serial.items()},
        "concurrent_stages_ms": {"sensor_fusion": q("fusion_ms", .5)},
        "observed_ms": {"p50": q("cycle_ms", .5), "p95": q("cycle_ms", .95),
                        "p99": q("cycle_ms", .99), "max": round(r["max"], 3),
                        "mean": round(r["mean"], 4),
                        "execution_time_sd": round(r["sd"], 4),         # dispersion of the execution time
                        "release_interval_sd": None if rel_sd is None else round(rel_sd, 4)},
        "sensor_age_ms": {"fusion_latency_p50": q("fusion_ms", .5), "fusion_latency_p95": q("fusion_ms", .95),
                          "fusion_period": 20.0, "max_observed_end_to_end": round(r["age_max"], 3)},
        "deadline_misses": r["misses"],
        "independent_blocks": blocks, "block_minutes": 100,
        "blocks_with_a_miss": blocks_with_miss,
        "block_miss_probability_upper_bound_95": upper,
        "block_bound_method": method,
        "per_cycle_bound_withdrawn": True,
        "why_withdrawn": "cycles are not independent trials; the bound is stated "
                         "at the block grain, where independence is defensible, "
                         "and is not converted back to a per-cycle figure",
        "fallback_chain": {"qp_retry_events": r["steps"][1],
                           "qp_retry_median_ms": round(float(np.median(ret)), 3) if ret.size else None,
                           "qp_retry_max_ms": round(float(ret.max()), 3) if ret.size else None,
                           "qp_retry_share_of_cycles": r["steps"][1] / r["n"],
                           "geometric_fallback_cycles": r["steps"][2],
                           "geometric_fallback_share": r["steps"][2] / r["n"]},
        "caveat": "observed distribution, not a WCET bound; see Section 9.2",
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
