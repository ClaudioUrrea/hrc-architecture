"""Control-loop timing over the timing campaign (Section: timing). Raw cycles only.

Cycle accounting is explicit: total cycles, cycles carrying an injected overrun (excluded from
the nominal distribution and reported as faults), retained cycles, and deadline misses in each
group. The block-level bound treats each cold-started run (block) as one independent trial.
"""
import numpy as np

import hrc_logs as H
from stats import zero_events_upper

STAGES = ["d_state_ns", "d_nominal_ns", "d_geo_ns", "d_learned_ns", "d_qp_ns", "d_dispatch_ns", "d_log_ns"]


def analyse(root, experiment="timing_campaign", allow_non_rt=False):
    runs = H.runs(root, experiment)
    if not runs:
        return None
    exec_ret, jitter, ages = [], [], []
    stage = {s: [] for s in STAGES}
    tot = inj = miss_ret = miss_inj = late = skipped = 0
    blocks = blocks_with_miss = 0
    excluded_non_rt, inputs = [], []
    for d in runs:
        m = H.manifest(d)
        if not m.get("rt_applied", {}).get("policy_ok", False) and not allow_non_rt:
            excluded_non_rt.append(d.name)
            continue
        c = H.cycles(d)
        inputs.append({"run": d.name, "manifest_sha256": H.hashlib.sha256((d / "MANIFEST.sha256").read_bytes()).hexdigest()})
        e = H.exec_ms(c).astype(np.float32)
        fin = np.isfinite(e)  # 3.1: the last record of a run has no recorded enqueue
        injm = H.flag(c, "injected_overrun")
        over = H.deadline_miss(c, H.period_ns(d))
        tot += len(c)
        inj += int(injm.sum())
        miss_ret += int((over & ~injm).sum())
        miss_inj += int((over & injm).sum())
        late += int(H.flag(c, "release_late").sum())
        skipped += H.skipped_releases(c, H.period_ns(d))
        exec_ret.append(e[~injm & fin])
        ri = H.release_interval_ms(c)
        ok = ~H.flag(c, "release_late")[1:]
        jitter.append(ri[ok].astype(np.float32))
        a = c["human_age_ms"]
        ages.append(a[a >= 0].astype(np.float32))
        for s in STAGES:
            stage[s].append(c[s][~injm].astype(np.float32) * 1e-6)
        blocks += 1
        blocks_with_miss += int((over & ~injm).any())
    if blocks == 0:
        return {"error": "no real-time runs", "excluded_non_rt": excluded_non_rt}
    E = np.concatenate(exec_ret)
    J = np.concatenate(jitter)
    A = np.concatenate(ages)
    q = lambda x, p: float(np.percentile(x, p))
    res = {
        "runs": blocks, "excluded_non_rt": excluded_non_rt,
        "cycles": {"total": tot, "with_injected_overrun_excluded": inj, "retained": tot - inj,
                   "deadline_misses_retained": miss_ret, "deadline_misses_in_injected": miss_inj,
                   "late_releases": late, "skipped_releases_from_t_release": skipped},
        "exec_endpoint": "enqueue completion (3.1 records); record completion (3.0 records)",
        "exec_ms": {"median": q(E, 50), "p95": q(E, 95), "p99": q(E, 99), "max": float(E.max()), "sd": float(E.std(ddof=1))},
        "release_interval_ms": {"mean": float(J.mean()), "sd": float(J.std(ddof=1))},
        "stage_median_ms": {s[2:-3]: q(np.concatenate(stage[s]), 50) for s in STAGES},
        "estimate_age_ms": {"median": q(A, 50), "p95": q(A, 95), "max": float(A.max())},
        "blocks": {"n": blocks, "with_retained_miss": blocks_with_miss,
                   "upper95_p_block_has_miss": zero_events_upper(blocks) if blocks_with_miss == 0 else None,
                   "rule_of_three": 3.0 / blocks if blocks_with_miss == 0 else None},
        "inputs": inputs,
    }
    return res
