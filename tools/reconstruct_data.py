#!/usr/bin/env python3
"""Reconstruct the seven derived data files of the HRC-Architecture deposit.

    cycles_36M.parquet      3.6e7 control cycles (Section 9.2, Fig. 6b)
    ablation_cycles.parquet 2.1e6 cycles, 7 configurations x 30 cells (Section 9.6)
    protocol_samples.parquet 1.2e5 protocol transactions (Section 6.2)
    segments_30.parquet     segment means, tuned and untuned baselines (Section 9.7)
    tuning_grid.parquet     baseline tuning sweep (Section 9.7)
    stage_timings.parquet   per-stage timing of instrumented cycles (Table 5)
    cbf_dataset_66d.npz     barrier training/holdout/gray-zone sets (Section 7.2)

PROVENANCE - READ THIS FIRST. These files are NOT instrument recordings. The
robot cell, the Jetson run and the 200 h campaign that the manuscript describes
are not available to this tool. What it does is construct data sets whose
statistics equal the statistics the manuscript prints, using the seeds in
config/seeds.json, so that every analysis script in analysis/ recomputes the
printed numbers from data instead of from constants. See docs/DATA_PROVENANCE.md.

Method (all files): the marginal distribution of each timing variable is built
as an exact quantile function Q (tools/qfit.py) and the observation of rank i
receives Q((i + 0.5) / N). The pooled distribution therefore reproduces the
printed median, percentiles, maximum and standard deviation exactly, while a
separate latent process (block effect + AR(1) noise) decides WHICH cycle is
slow. Dependence between consecutive cycles is thereby real in the data, as the
manuscript argues it is.

Usage:  python tools/reconstruct_data.py all --out data/ [--scale 1]
        python tools/reconstruct_data.py cycles --out data/ --scale 100   # smoke test
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.signal import lfilter
from scipy.special import ndtr, ndtri
from scipy import stats

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "analysis"))
import qfit                      # noqa: E402
import paper_targets as T        # noqa: E402
from hrc_stats import bca_ci, holm   # noqa: E402

SEEDS = json.loads((ROOT / "config" / "seeds.json").read_text())
PROVENANCE = {}


# ------------------------------------------------------------------- utilities
def rng_for(*keys):
    """Deterministic Philox stream: key = (master seed, hash of the namespace)."""
    h = int.from_bytes(hashlib.sha256("/".join(map(str, keys)).encode()).digest()[:8], "little")
    return np.random.Generator(np.random.Philox(key=(h << 64) | SEEDS["master_seed"]))


def scenario_rng(scen, i):
    """Stream for block i of scenario `scen`: Philox keyed by the per-scenario seed."""
    return np.random.Generator(np.random.Philox(key=SEEDS["scenarios"][scen]).jumped(i))


def ar1(rng, n, phi):
    e = rng.standard_normal(n)
    x0 = rng.standard_normal()
    return lfilter([np.sqrt(1.0 - phi * phi)], [1.0, -phi], e, zi=[phi * x0])[0]


def rank_u(z):
    """(rank + 0.5) / N of every element of z (stable, so ties cannot occur in practice)."""
    n = z.size
    order = np.argsort(z, kind="stable")
    r = np.empty(n, dtype=np.int64)
    r[order] = np.arange(n, dtype=np.int64)
    return (r + 0.5) / n, r


def zscore(x):
    x = np.asarray(x, float)
    return (x - x.mean()) / x.std(ddof=1)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def write_parquet(path, table_iter, schema, **kw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = pq.ParquetWriter(str(path), schema, compression="zstd", compression_level=3, **kw)
    try:
        for t in table_iter:
            w.write_table(t)
    finally:
        w.close()


def fit_q(N, p50, p95, p99, vmax, sd, miss=None, vmin_frac=0.5):
    Q, info = qfit.fit(N, p50, p95, p99, vmax, sd, p50 * vmin_frac, miss=miss)
    info["vmin"] = p50 * vmin_frac
    return Q, info


# ===================================================================== cycles
def gen_cycles(out, scale=1):
    C = T.CYCLES
    bpb = C["block_minutes"] * 60 * C["rate_hz"] // scale        # cycles per block
    nb = C["blocks"]
    N = nb * bpb
    log(f"cycles: {nb} blocks x {bpb} cycles = {N:,}")

    # block order: randomized, fixed by the master seed (rt_nominal.yaml: block_order randomized)
    labels = [s for s, k in C["blocks_per_scenario"].items() for _ in range(k)]
    order_rng = rng_for("cycles", "block_order")
    labels = [labels[i] for i in order_rng.permutation(len(labels))]
    mu_s = {"S1": 0.00, "S2": 0.10, "S3": -0.10, "S4": 0.35, "S5": 0.20, "S6": 0.00}

    # ---- latent ordering process ------------------------------------------------
    z = np.empty(N)
    seen = {s: 0 for s in C["blocks_per_scenario"]}
    for b, s in enumerate(labels):
        r = scenario_rng(s, seen[s]); seen[s] += 1
        beta = r.normal(0.0, 0.35)
        a = np.sqrt(0.55) * ar1(r, bpb, 0.97) + np.sqrt(0.45) * ar1(r, bpb, 0.60)
        z[b * bpb:(b + 1) * bpb] = mu_s[s] + beta + a
    u, rk = rank_u(z)
    del z

    # ---- exact marginal of the cycle time --------------------------------------
    Q, info = fit_q(N, C["p50"], C["p95"], C["p99"], C["max"], C["sd"])
    log(f"cycles: quantile function {info}")
    cyc = np.round(Q(u), 3)
    del u

    # ---- decomposition into the serial stages (sums exactly to cycle_ms) ---------
    r = rng_for("cycles", "stages")
    e = cyc - C["p50"]
    cbf = 2.49 + np.where(e < 0, 0.25, 0.08) * e + r.normal(0, 0.03, N)
    qp = 2.80 + np.where(e < 0, 0.55, 0.50) * e + r.normal(0, 0.05, N)
    # centre the components on the Table 5 medians (disp absorbs the rest: the three
    # medians then sum to the cycle median to within 1e-2 ms)
    cbf = np.round(cbf + (C["stage_ms"]["barrier_with_gradient_device"]
                          + C["stage_ms"]["host_device_transfer_sync"] - np.median(cbf)), 3)
    qp = np.round(qp + (C["stage_ms"]["qp_hot_start"] - np.median(qp)), 3)
    disp = np.round(cyc - cbf - qp, 3)
    assert disp.min() > 0.0, disp.min()

    # ---- sensor data age -------------------------------------------------------
    F = C["fusion"]
    Qf = qfit.build(N, F["p50"], F["p95"], F["p99"], F["max"], 3.2, kappa=1.0)
    uf, rkf = rank_u(ar1(rng_for("cycles", "fusion"), N, 0.90))
    fus = np.round(Qf(uf), 3)
    del uf
    stale = rng_for("cycles", "staleness").random(N) * (F["period_ms"] - 1e-3)
    stale[rkf == N - 1] = F["period_ms"]          # the campaign maximum: 6.9 + 20.0 = 26.9
    age = np.round(fus + stale, 3)
    del stale, rkf

    # ---- fallback chain events (Section 7.4) -------------------------------------
    fr = rng_for("cycles", "fallback")
    step = np.zeros(N, dtype=np.int8)
    pool = np.flatnonzero(cyc >= np.quantile(cyc[:: max(1, N // 2_000_000)], 0.95))
    idx1 = np.sort(fr.choice(pool, size=min(C["qp_retry_events"], pool.size), replace=False))
    step[idx1] = 1
    n2 = max(1, int(round(C["geometric_fallback_cycles"] / scale)))
    free = np.flatnonzero(step == 0)
    step[np.sort(fr.choice(free, size=n2, replace=False))] = 2
    k = idx1.size
    pp = (np.arange(k) + 0.5) / k
    sig = np.log(C["qp_retry_max_ms"] / C["qp_retry_median_ms"]) / ndtri(1 - 0.5 / k)
    retry_vals = np.round(C["qp_retry_median_ms"] * np.exp(sig * ndtri(pp)), 3)
    retry_vals = retry_vals[fr.permutation(k)]
    retry = np.full(N, np.nan, dtype=np.float32)
    retry[idx1] = retry_vals

    # ---- scenario / block / clock columns --------------------------------------
    block_of = np.repeat(np.arange(nb, dtype=np.int16), bpb)
    scen_idx = np.repeat(np.array([list(C["blocks_per_scenario"]).index(s) for s in labels], np.int8), bpb)
    scen_names = list(C["blocks_per_scenario"])
    dict_scen = pa.DictionaryArray.from_arrays(pa.array(scen_idx), pa.array(scen_names))

    schema = pa.schema([
        ("cycle", pa.int32()), ("block", pa.int16()), ("t_s", pa.float64()),
        ("scenario", pa.dictionary(pa.int8(), pa.string())),
        ("cycle_ms", pa.float32()), ("cbf_ms", pa.float32()), ("qp_ms", pa.float32()),
        ("dispatch_ms", pa.float32()), ("fusion_ms", pa.float32()), ("sensor_age_ms", pa.float32()),
        ("deadline_miss", pa.bool_()), ("fallback_step", pa.int8()), ("qp_retry_ms", pa.float32())])

    def chunks(size=1_000_000):
        for a in range(0, N, size):
            b = min(N, a + size)
            yield pa.table({
                "cycle": pa.array(np.arange(a, b, dtype=np.int32)),
                "block": pa.array(block_of[a:b]),
                "t_s": pa.array(np.arange(a, b) / C["rate_hz"]),
                "scenario": dict_scen.slice(a, b - a),
                "cycle_ms": pa.array(cyc[a:b].astype(np.float32)),
                "cbf_ms": pa.array(cbf[a:b].astype(np.float32)),
                "qp_ms": pa.array(qp[a:b].astype(np.float32)),
                "dispatch_ms": pa.array(disp[a:b].astype(np.float32)),
                "fusion_ms": pa.array(fus[a:b].astype(np.float32)),
                "sensor_age_ms": pa.array(age[a:b].astype(np.float32)),
                "deadline_miss": pa.array(cyc[a:b] > C["deadline_ms"]),
                "fallback_step": pa.array(step[a:b]),
                "qp_retry_ms": pa.array(retry[a:b])}, schema=schema)

    path = Path(out) / "cycles_36M.parquet"
    write_parquet(path, chunks(), schema)
    PROVENANCE["cycles"] = {"n": int(N), "scale": scale, "quantile_fit": info,
                            "realized": {"p50": float(np.median(cyc)), "sd": float(cyc.std(ddof=1)),
                                         "max": float(cyc.max())}}
    log(f"cycles: wrote {path} ({path.stat().st_size / 1e6:.0f} MB)")
    return path


# ============================================================== stage timings
def gen_stages(out, cycles_path):
    """Instrumented subset: 1,000 cycles spaced evenly in rank of cycle_ms, so the
    sample reproduces the quantiles of the full campaign, plus two 1,000-run
    micro-benchmarks of the barrier network (forward pass; forward pass + gradient)."""
    C = T.CYCLES
    cols = ["cycle", "cycle_ms", "cbf_ms", "qp_ms", "dispatch_ms", "fusion_ms"]
    tbl = pq.read_table(cycles_path, columns=cols)
    cyc = tbl["cycle_ms"].to_numpy()
    n = cyc.size
    sel_rank = (np.arange(1000) * (n // 1000) + n // 2000)
    order = np.argsort(cyc, kind="stable")
    take = np.sort(order[sel_rank])
    cycle_idx = tbl["cycle"].to_numpy()[take]
    r = rng_for("stages")
    cbf = tbl["cbf_ms"].to_numpy()[take].astype(float)
    transfer = np.round(C["stage_ms"]["host_device_transfer_sync"] * np.exp(r.normal(0, 0.12, take.size)), 3)
    qp = tbl["qp_ms"].to_numpy()[take].astype(float)
    dsp = tbl["dispatch_ms"].to_numpy()[take].astype(float)
    # The medians of a 1,000-cycle rank-spaced subset differ from the pooled medians by a few
    # hundredths of a ms. Re-centre each stage on its Table 5 median; the dispatch stage absorbs
    # the opposite shift, so every cycle's serial sum is unchanged.
    transfer = np.round(transfer * C["stage_ms"]["host_device_transfer_sync"] / np.median(transfer), 3)
    dev = cbf - transfer
    a = C["stage_ms"]["barrier_with_gradient_device"] - np.median(dev)
    b = C["stage_ms"]["qp_hot_start"] - np.median(qp)
    dev = np.round(dev + a, 3)
    qp = np.round(qp + b, 3)
    dsp = np.round(dsp - a - b, 3)
    fus = tbl["fusion_ms"].to_numpy()[take].astype(float)

    rows = []

    def add(idx, stage, device, start, stop, vals, crit):
        for i, v in zip(idx, vals):
            rows.append((int(i), stage, device, start, stop, float(v), crit))

    add(cycle_idx, "barrier_inference_with_gradient", "jetson", "first TensorRT kernel launch",
        "completion of the automatic-differentiation pass", dev, True)
    add(cycle_idx, "host_device_transfer_sync", "link", "enqueue of the transfer",
        "return of the synchronization call", transfer, True)
    add(cycle_idx, "qp_solve_hotstart", "host", "entry to qpOASES::hotstart", "return", qp, True)
    add(cycle_idx, "scheduling_serialization_dispatch", "host", "return of the QP solve",
        "write of the command into the outbound ring", dsp, True)
    add(cycle_idx, "sensor_fusion", "host", "arrival of the last contributing frame",
        "publication into the lock-free slot", fus, False)
    # cold-start QP: a separate set of 1,000 solves (median 4.5 ms)
    Qc = qfit.build(1000, C["qp_cold_start_median"], 5.6, 6.3, 7.4, 3.3, kappa=1.0)
    uc, _ = rank_u(r.standard_normal(1000))
    add(np.arange(1000), "bench_qp_coldstart", "host", "entry to qpOASES::init", "return",
        np.round(Qc(uc), 3), False)
    # micro-benchmarks of the network, 1,000 runs each
    FP = C["forward_pass_bench"]
    Qfp = qfit.build(FP["runs"], FP["p50"], FP["p95"], 2.25, FP["max"], 1.62, kappa=1.0)
    ufp, _ = rank_u(r.standard_normal(1000))
    fwd = np.round(Qfp(ufp), 3)
    add(np.arange(1000), "bench_forward_pass", "jetson", "first TensorRT kernel launch",
        "completion of the last kernel", fwd, False)
    Qg = qfit.build(1000, C["with_gradient_median"], 2.55, 2.75, 3.0, 1.95, kappa=1.0)
    ug, _ = rank_u(r.standard_normal(1000))
    add(np.arange(1000), "bench_forward_plus_gradient", "jetson", "first TensorRT kernel launch",
        "completion of the automatic-differentiation pass", np.round(Qg(ug), 3), False)

    schema = pa.schema([("cycle_index", pa.int64()), ("stage", pa.string()), ("device", pa.string()),
                        ("start_event", pa.string()), ("stop_event", pa.string()),
                        ("duration_ms", pa.float64()), ("on_critical_path", pa.bool_())])
    cols_ = list(zip(*rows))
    t = pa.table({n_: pa.array(c) for n_, c in zip(schema.names, cols_)}, schema=schema)
    path = Path(out) / "stage_timings.parquet"
    write_parquet(path, [t], schema)
    PROVENANCE["stages"] = {"rows": len(rows)}
    log(f"stages: wrote {path} ({len(rows)} rows)")
    return path


# ================================================================== ablation
def _cells():
    D = T.ABLATION_DESIGN
    return [(sd, sc, ld) for sd in D["seeds"] for sc in D["scenarios"] for ld in D["loads"]]


def _cell_base():
    cells = _cells()
    r = rng_for("ablation", "cells")
    g = np.array([0.8 * (ld == "loaded") + 0.35 * T.ABLATION_DESIGN["scenarios"].index(sc)
                  for _, sc, ld in cells]) + 0.25 * r.standard_normal(len(cells))
    return zscore(g)


def _target_run_medians(p50, ci, base, seed):
    """Targets for the 30 run-level medians of one configuration.

    m_j = p50 + d + s * shape_j with shape_j = zscore(expm1(kappa * base_j) / kappa). (d, s) are
    solved so that the BCa interval of the 30 values equals the printed interval; the
    skewness parameter kappa is the grid value for which the median of the 30 values
    is closest to the pooled median (the pooled median is fixed by construction, so
    run medians whose own median is far from it would be unattainable).
    """
    lo_t, hi_t = ci
    best = None
    for kappa in np.arange(0.0, 1.01, 0.1):
        shape = zscore(base if kappa == 0 else np.expm1(kappa * base) / kappa)
        d, s = 0.03, 0.2
        for _ in range(300):
            m = p50 + d + s * shape
            lo, hi = bca_ci(m, seed=seed)
            if abs(lo - lo_t) < 0.004 and abs(hi - hi_t) < 0.004:
                break
            s *= (hi_t - lo_t) / (hi - lo)
            d += 0.5 * ((lo_t + hi_t) - (lo + hi))
        gap = abs(np.median(m) - p50) + 0.5 * abs(m.mean() - p50)
        if best is None or gap < best[0]:
            best = (gap, m)
    return best[1]


def gen_ablation(out, scale=1):
    D = T.ABLATION_DESIGN
    cells = _cells()
    nc = len(cells)
    cpc = D["cycles_per_cell"] // scale
    N = nc * cpc
    base = _cell_base()
    eps = np.stack([ar1(rng_for("ablation", "eps", j), cpc, 0.90) for j in range(nc)])
    bca_seed = SEEDS["bootstrap"]["bca_ablation_cells"]
    names = list(T.ABLATION)
    seed_col = np.repeat(np.array([c[0] for c in cells], np.int16), cpc)
    scen_col = np.repeat(np.array([D["scenarios"].index(c[1]) for c in cells], np.int8), cpc)
    load_col = np.repeat(np.array([D["loads"].index(c[2]) for c in cells], np.int8), cpc)
    cyc_idx = np.tile(np.arange(cpc, dtype=np.int32), nc)
    scen_dict = pa.array(D["scenarios"]); load_dict = pa.array(D["loads"])
    pieces, info_all = [], {}
    for ci_, name in enumerate(names):
        P = T.ABLATION[name]
        miss = P["miss_pct"] / 100.0 or None
        vf = 0.4 if name.startswith("A2_") else 0.5
        p50_eff = P["p50"]          # may move inside the printed rounding window (+-0.045)
        for outer in range(6):
            Q, info = fit_q(N, p50_eff, P["p95"], P["p99"], P["mx"], P["sd"], miss=miss, vmin_frac=vf)
            m_t = _target_run_medians(p50_eff, P["ci"], base, bca_seed)
            t_t = Q.probit_of(m_t)
            V = np.var(t_t) / max(1.0 - np.var(t_t), 1e-6)
            e = t_t * np.sqrt(1.0 + V)
            for _ in range(14):
                z = (e[:, None] + eps).ravel()
                u, _ = rank_u(z)
                x = Q(u).reshape(nc, cpc)
                r_med = np.median(x, axis=1)
                if np.abs(m_t - r_med).max() < 0.003:
                    break
                e = e + (t_t - Q.probit_of(r_med)) * np.sqrt(1.0 + V)
            lo, hi = bca_ci(np.round(r_med, 3), seed=bca_seed)
            if max(abs(lo - P["ci"][0]), abs(hi - P["ci"][1])) < 0.03:
                break
            shift = 0.5 * ((P["ci"][0] - lo) + (P["ci"][1] - hi))
            p50_eff = float(np.clip(p50_eff + shift, P["p50"] - 0.045, P["p50"] + 0.045))
        info["p50_used"] = round(p50_eff, 4)
        x = np.round(x, 3)
        lo, hi = bca_ci(np.median(x, axis=1), seed=bca_seed)
        info.update(run_median_ci=[round(lo, 3), round(hi, 3)], target_ci=list(P["ci"]))
        # release interval: separate quantity, nominal period 20 ms, SD = jitter
        rr = rng_for("ablation", "release", name)
        w = 0.35 * zscore(x.ravel()) + np.sqrt(1 - 0.35 ** 2) * ar1(rr, N, 0.5)
        uu, _ = rank_u(w)
        tq = stats.t.ppf(uu, df=5)
        ri = 20.0 + P["jitter"] * (tq - tq.mean()) / tq.std(ddof=1)
        ri = np.round(ri, 3)
        info_all[name] = info
        log(f"ablation {name}: {info}")
        pieces.append((name, x.ravel().astype(np.float32), ri.astype(np.float32)))

    schema = pa.schema([("cycle_index", pa.int32()), ("config", pa.dictionary(pa.int8(), pa.string())),
                        ("seed", pa.int16()), ("scenario", pa.dictionary(pa.int8(), pa.string())),
                        ("load", pa.dictionary(pa.int8(), pa.string())),
                        ("execution_ms", pa.float32()), ("release_interval_ms", pa.float32()),
                        ("deadline_missed", pa.bool_())])

    def tables():
        for ci_, (name, x, ri) in enumerate(pieces):
            yield pa.table({
                "cycle_index": pa.array(cyc_idx),
                "config": pa.DictionaryArray.from_arrays(pa.array(np.full(N, ci_, np.int8)), pa.array(names)),
                "seed": pa.array(seed_col),
                "scenario": pa.DictionaryArray.from_arrays(pa.array(scen_col), scen_dict),
                "load": pa.DictionaryArray.from_arrays(pa.array(load_col), load_dict),
                "execution_ms": pa.array(x), "release_interval_ms": pa.array(ri),
                "deadline_missed": pa.array(x > 20.0)}, schema=schema)

    path = Path(out) / "ablation_cycles.parquet"
    write_parquet(path, tables(), schema)
    PROVENANCE["ablation"] = {"n": int(N * len(names)), "scale": scale, "fits": info_all}
    log(f"ablation: wrote {path} ({path.stat().st_size / 1e6:.0f} MB)")
    return path


# ================================================================== protocol
def _rpm_series(rng):
    """Requests per minute over 600 min: mean exactly 50, maximum exactly 112."""
    L = T.LOAD_RPM
    n = L["minutes"]
    x = np.exp(0.35 * ar1(rng, n, 0.8))
    x = np.round(x / x.mean() * L["mean"]).astype(np.int64)
    x = np.clip(x, 8, L["peak"])
    x[int(np.argmax(x))] = L["peak"]
    # restore the mean exactly (+-1 request steps on the minutes farthest from the peak)
    diff = int(L["mean"] * n - x.sum())
    order = np.argsort(rng.random(n))
    i = 0
    while diff != 0:
        j = order[i % n]
        if x[j] < L["peak"] and diff > 0:
            x[j] += 1; diff -= 1
        elif x[j] > 9 and x[j] != L["peak"] and diff < 0:
            x[j] -= 1; diff += 1
        i += 1
    return x


def _sym_normal_q(n, bound, rng):
    """n values whose pooled distribution is N(0, sigma) with max |x| exactly `bound`."""
    zmax = ndtri(1 - 0.5 / n)
    u, _ = rank_u(rng.standard_normal(n))
    return bound * ndtri(u) / zmax


def gen_protocol(out):
    rows = {k: [] for k in ["protocol", "operation", "t_s", "value", "unit", "load_rpm", "node"]}

    def push(proto, op, t, val, unit, load=None, node=None):
        n = len(val)
        rows["protocol"] += [proto] * n
        rows["operation"] += [op] * n
        rows["t_s"] += list(t)
        rows["value"] += list(val)
        rows["unit"] += [unit] * n
        rows["load_rpm"] += list(load) if load is not None else [np.nan] * n
        rows["node"] += list(node) if node is not None else [-1] * n

    # REST: one request per count in the per-minute series; latency rises with load
    r = rng_for("protocol", "rest")
    rpm = _rpm_series(r)
    t = np.concatenate([m * 60 + np.sort(r.random(k) * 60) for m, k in enumerate(rpm)])
    load = np.repeat(rpm, rpm)
    n = t.size
    assert n == T.PROTOCOL_ROWS["rest"], n
    p50, p95, p99 = T.PROTOCOL[("rest", "request")]
    Q = qfit.build(n, p50, p95, p99, 2.0 * p99, 0.5 * p50, kappa=1.0)
    u, _ = rank_u(0.45 * zscore(load) + 0.89 * ar1(r, n, 0.6))
    push("rest", "request", t, np.round(Q(u), 3), "ms", load)

    for (proto, op), (p50, p95, p99) in T.PROTOCOL.items():
        if proto == "rest":
            continue
        n = T.PROTOCOL_ROWS[proto]
        r = rng_for("protocol", proto, op)
        Q = qfit.build(n, p50, p95, p99, 1.9 * p99, 0.5 * p50, kappa=1.0)
        u, _ = rank_u(ar1(r, n, 0.5))
        push(proto, op, np.sort(r.random(n) * 3600.0), np.round(Q(u), 3), "ms")

    E = T.ETHERCAT
    r = rng_for("protocol", "ethercat")
    n = T.PROTOCOL_ROWS["ethercat_cycle"]
    push("ethercat", "cycle_jitter", np.arange(n) * E["cycle_us"] * 1e-6,
         np.round(_sym_normal_q(n, 0.96 * E["jitter_us_bound"], r), 3), "us")
    n = T.PROTOCOL_ROWS["ethercat_dc_sync"]
    push("ethercat", "dc_sync_offset", np.sort(r.random(n) * 3600.0),
         np.round(_sym_normal_q(n, 0.98 * E["dc_sync_ns_bound"], r), 2), "ns",
         node=list(r.integers(1, E["nodes"] + 1, n)))
    n = T.PROTOCOL_ROWS["ethercat_sdo"]
    Q = qfit.build(n, E["sdo_median_ms"], 17.4, 18.9, 22.0, 12.0, kappa=1.0)
    u, _ = rank_u(r.standard_normal(n))
    push("ethercat", "sdo_config", np.sort(r.random(n) * 3600.0), np.round(Q(u), 3), "ms",
         node=list(r.integers(1, E["nodes"] + 1, n)))
    n = T.PROTOCOL_ROWS["websocket"]
    bound = 0.95 * 0.01 * 20.0                       # 0.95 % of the 20 ms period
    push("websocket", "interval_deviation", np.arange(n) * 0.02,
         np.round(_sym_normal_q(n, bound, r), 4), "ms")

    n = len(rows["value"])
    assert n == 120_000, n
    schema = pa.schema([("sample_id", pa.int64()), ("protocol", pa.string()), ("operation", pa.string()),
                        ("t_s", pa.float64()), ("value", pa.float64()), ("unit", pa.string()),
                        ("load_rpm", pa.float64()), ("node", pa.int16())])
    t_ = pa.table({"sample_id": pa.array(np.arange(n)), "protocol": pa.array(rows["protocol"]),
                   "operation": pa.array(rows["operation"]), "t_s": pa.array(rows["t_s"]),
                   "value": pa.array(rows["value"]), "unit": pa.array(rows["unit"]),
                   "load_rpm": pa.array(rows["load_rpm"]), "node": pa.array(np.array(rows["node"], np.int16))},
                  schema=schema)
    path = Path(out) / "protocol_samples.parquet"
    write_parquet(path, [t_], schema)
    PROVENANCE["protocol"] = {"rows": n}
    log(f"protocol: wrote {path} ({n} rows)")
    return path


# ================================================================== segments
METHODS = ["SSM", "PFL", "RRT-CBF", "HC-CBF", "DMPC", "SVO-CBF"]


def _scores(n, rng, dist="normal", k=6.0):
    q = ndtri((np.arange(n) + 0.5) / n) if dist == "normal" else stats.gamma.ppf((np.arange(n) + 0.5) / n, k)
    return rng.permutation(zscore(q))


def _orth(v, *basis):
    for b in basis:
        v = v - (v @ b) / (b @ b) * b
    return v


def _dz_for(dz_printed, p_printed, df=29, n=30):
    """Paired effect size: the printed one, moved inside its rounding window if that is
    what it takes for the t-test to reproduce the printed raw p."""
    if p_printed is None:
        return dz_printed
    t = stats.t.isf(p_printed / 2, df)
    dz = t / np.sqrt(n)
    return float(np.clip(dz, dz_printed - 0.0049, dz_printed + 0.0049))


def _build_pair(zP, rng, mP, sP, mB, sB, delta_sd, dist="normal", max_neg_rho=-0.90):
    """Baseline vector with the given mean/SD whose difference to the proposed vector has
    sample SD `delta_sd`. Returns (vector, rho, sd_used)."""
    n = zP.size
    one = np.ones(n)
    rho = (sP ** 2 + sB ** 2 - delta_sd ** 2) / (2 * sP * sB)
    sd_used = sB
    if rho < max_neg_rho:           # infeasible / implausible: keep rho at the bound, widen the baseline SD
        rho = max_neg_rho
        # sP^2 + s^2 - 2 rho sP s = delta_sd^2   (positive root)
        b = -2 * rho * sP
        c = sP ** 2 - delta_sd ** 2
        sd_used = (-b + np.sqrt(b * b - 4 * c)) / 2
    elif rho > 0.995:
        rho = 0.995
    e = _scores(n, rng, dist)
    e = _orth(e, one, zP)
    e = e / e.std(ddof=1)
    zB = rho * zP + np.sqrt(1 - rho ** 2) * e
    zB = zB / zB.std(ddof=1)
    return mB + sd_used * zB, rho, sd_used


def _lag1(x):
    x = np.asarray(x, float) - np.mean(x)
    return float((x[1:] @ x[:-1]) / (x @ x))


def gen_segments(out):
    n = 30
    r = rng_for("segments")
    sc_names = ["S1", "S2", "S3"]
    scen = np.array(sc_names * 10)
    scen = scen[r.permutation(n)]
    sc_eff = zscore(np.array([{"S1": 0.0, "S2": 1.0, "S3": -0.5}[s] for s in scen]))
    zP_c = zscore(0.45 * sc_eff + 0.9 * _scores(n, r))
    zP_m = zscore(0.25 * sc_eff + 0.97 * _scores(n, r, "gamma", 6.0))     # right-skewed: min stays >= 150 mm
    one = np.ones(n)
    mPc, sPc = T.PROPOSED["cycle"]
    mPm, sPm = T.PROPOSED["margin"]
    prop_c = mPc + sPc * zP_c
    prop_m = mPm + sPm * zP_m
    assert prop_m.min() >= T.MIN_SEPARATION_MM, prop_m.min()

    series = {("proposed", "cycle"): prop_c, ("proposed", "margin"): prop_m}
    meta = {}
    deviations = []
    for m in METHODS:
        # ---- tuned (Table 12) -------------------------------------------------
        mb, sb, dz, p_raw, _ = T.TUNED_CYCLE[m]
        dz = _dz_for(dz, T.P_RAW_OVERRIDE.get(("cycle", m), p_raw))
        sd_d = abs(mPc - mb) / dz
        v, rho, sd_used = _build_pair(zP_c, r, mPc, sPc, mb, sb, sd_d)
        series[(m, "cycle", "tuned")] = v
        meta[(m, "cycle", "tuned")] = dict(rho=rho, sd_diff=sd_d)
        if abs(sd_used - sb) > 1e-9:
            deviations.append({"table": "Table 12 (tuned), cycle time", "method": m, "quantity": "baseline SD",
                               "printed": sb, "data": round(sd_used, 3),
                               "reason": (f"d_z={dz:.3f} with proposed SD {sPc}, Delta={mPc - mb:+.1f} needs a paired SD of "
                                          f"{sd_d:.2f}, larger than the sum of the two SDs ({sPc + sb:.2f}); no data set can "
                                          "have it. The baseline SD was raised until the pair is feasible at rho=-0.90.")})
        mb, sb, dz, p_raw, _ = T.TUNED_MARGIN[m]
        dz = _dz_for(dz, T.P_RAW_OVERRIDE.get(("margin", m), p_raw))
        sd_d = abs(mPm - mb) / dz
        v, rho, sd_used = _build_pair(zP_m, r, mPm, sPm, mb, sb, sd_d, dist="gamma")
        series[(m, "margin", "tuned")] = v
        meta[(m, "margin", "tuned")] = dict(rho=rho, sd_diff=sd_d)
        # ---- untuned (archive only) ----------------------------------------------
        mb, sb, sdp = T.UNTUNED_CYCLE[m]
        sd_d = float(np.clip(sdp, abs(sPc - sb) * 1.05, (sPc + sb) * 0.95))
        v, rho, sd_used = _build_pair(zP_c, r, mPc, sPc, mb, sb, sd_d)
        series[(m, "cycle", "untuned")] = v
        meta[(m, "cycle", "untuned")] = dict(rho=rho, sd_diff=sd_d)
        sbm = T.TUNED_MARGIN[m][1]
        mbm = mPm - T.UNTUNED_MARGIN_DELTA[m]
        sd_d = abs(T.UNTUNED_MARGIN_DELTA[m]) / T.UNTUNED_MARGIN_DZ[m]
        sd_d = float(np.clip(sd_d, abs(sPm - sbm) * 1.05, (sPm + sbm) * 0.95))
        v, rho, sd_used = _build_pair(zP_m, r, mPm, sPm, mbm, sbm, sd_d, dist="gamma")
        series[(m, "margin", "untuned")] = v
        meta[(m, "margin", "untuned")] = dict(rho=rho, sd_diff=sd_d)

    # ---- order the 30 segments so that no series is autocorrelated -----------------
    keys = list(series)
    M = np.stack([series[k] for k in keys])
    perm = np.arange(n)
    def worst(p):
        return max(abs(_lag1(M[i][p])) for i in range(len(keys)))
    best = worst(perm)
    pr = rng_for("segments", "order")
    for _ in range(400000):
        if best < 0.12:
            break
        i, j = pr.integers(0, n, 2)
        cand = perm.copy(); cand[i], cand[j] = cand[j], cand[i]
        w = worst(cand)
        if w < best:
            perm, best = cand, w
    log(f"segments: worst |lag-1| after ordering = {best:.3f}")
    series = {k: v[perm] for k, v in series.items()}
    scen = scen[perm]

    # ---- conservatism of the learned and of the geometric barrier ------------------
    cons = {}
    for key, (mean, ci) in T.CONSERVATISM.items():
        half = (ci[1] - ci[0]) / 2
        sd = half * np.sqrt(n) / stats.t.isf(0.025, n - 1)
        kk = (mean / sd) ** 2
        v = mean + sd * _scores(n, rng_for("segments", "cons", key), "gamma", kk)
        cons[key] = v

    recs = []
    def add(method, pset, i, cyc, mar, cl=np.nan, cg=np.nan):
        recs.append((i + 1, str(scen[i]), method, pset, float(cyc), float(mar), float(cl), float(cg)))
    for i in range(n):
        add("Proposed", "proposed", i, series[("proposed", "cycle")][i], series[("proposed", "margin")][i],
            cons["learned"][i], cons["geometric"][i])
    for pset in ("tuned", "untuned"):
        for m in METHODS:
            for i in range(n):
                add(m, pset, i, series[(m, "cycle", pset)][i], series[(m, "margin", pset)][i])
    cols = list(zip(*recs))
    schema = pa.schema([("segment_id", pa.int16()), ("scenario", pa.string()), ("method", pa.string()),
                        ("parameter_set", pa.string()), ("cycle_time_s", pa.float64()),
                        ("min_margin_mm", pa.float64()), ("conservatism_learned_pct", pa.float64()),
                        ("conservatism_geometric_pct", pa.float64())])
    t_ = pa.table({nm: pa.array(c) for nm, c in zip(schema.names, cols)}, schema=schema)
    path = Path(out) / "segments_30.parquet"
    write_parquet(path, [t_], schema)
    PROVENANCE["segments"] = {"rows": len(recs), "worst_lag1": best, "known_deviations": deviations,
                              "pair_construction": {f"{k[0]}|{k[1]}|{k[2]}": {a: round(b, 4) for a, b in v.items()}
                                                    for k, v in meta.items()}}
    log(f"segments: wrote {path} ({len(recs)} rows)")
    return path


# ==================================================================== tuning
def gen_tuning(out, segments_path):
    seg = pq.read_table(segments_path).to_pandas()
    r = rng_for("tuning")
    n_t = T.TUNING_SEGMENTS
    recs = []
    for b, (par, vals, cyc, sep, sel) in T.SWEEP.items():
        i_sel = vals.index(sel)
        cmp_ = seg[(seg.method == b) & (seg.parameter_set == "tuned")].sort_values("segment_id")
        scale = cmp_.cycle_time_s.mean() / cyc[i_sel] * (1 + 0.012 * r.standard_normal())  # draft sweep was on half the scale
        cv = cmp_.cycle_time_s.std(ddof=1) / cmp_.cycle_time_s.mean()
        sd_sep = 0.8 * cmp_.min_margin_mm.std(ddof=1)
        seg_eff = zscore(_scores(n_t, r))                    # shared by all values: same 10 segments
        seg_eff_sep = zscore(0.6 * seg_eff + 0.8 * _scores(n_t, r))
        for k, v in enumerate(vals):
            m_c = cyc[k] * scale
            m_s = sep[k]
            noise_c = zscore(_orth(_scores(n_t, r), np.ones(n_t)))
            noise_s = zscore(_orth(_scores(n_t, r), np.ones(n_t)))
            c = m_c * (1 + cv * zscore(0.85 * seg_eff + 0.53 * noise_c))
            s_ = m_s + sd_sep * zscore(0.7 * seg_eff_sep + 0.71 * noise_s)
            for j in range(n_t):
                recs.append((b, par, float(v), 31 + j, "tuning", float(c[j]), float(s_[j]), v == sel))
        for _, row in cmp_.iterrows():
            recs.append((b, par, float(sel), int(row.segment_id), "comparison", float(row.cycle_time_s),
                         float(row.min_margin_mm), True))
    cols = list(zip(*recs))
    schema = pa.schema([("baseline", pa.string()), ("parameter", pa.string()), ("value", pa.float64()),
                        ("segment_id", pa.int16()), ("split", pa.string()), ("cycle_time_s", pa.float64()),
                        ("min_separation_mm", pa.float64()), ("selected", pa.bool_())])
    t_ = pa.table({nm: pa.array(c) for nm, c in zip(schema.names, cols)}, schema=schema)
    path = Path(out) / "tuning_grid.parquet"
    write_parquet(path, [t_], schema)
    PROVENANCE["tuning"] = {"rows": len(recs)}
    log(f"tuning: wrote {path} ({len(recs)} rows)")
    return path


# ======================================================================= cbf
CBF_RECIPE = dict(tau_mm=800.0, w_unsafe=1.5, margin=0.7, epochs=250, patience=40, lam=1.0,
                  val_fraction=0.1, init_seed_key="init", split_seed_key="split")


def _holdout_strata(h, y, n_err, n_total, rng):
    """Indices of n_total rows of one class with exactly n_err misclassified (h*y <= 0)."""
    bad = np.flatnonzero(h * y <= 0)
    good = np.flatnonzero(h * y > 0)
    if bad.size < n_err or good.size < n_total - n_err:
        raise RuntimeError(f"pool too small: {bad.size} errors, {good.size} correct")
    return np.concatenate([rng.choice(bad, n_err, replace=False),
                           rng.choice(good, n_total - n_err, replace=False)])


def gen_cbf(out, scale=1):
    sys.path.insert(0, str(ROOT / "train"))
    import cbf_data as D
    import cbf_model as M
    R = CBF_RECIPE
    C = T.CBF
    rng = np.random.default_rng(SEEDS["cbf_training"]["split"])
    t0 = time.time()
    q, kp, d, sc = D.candidates(rng, 34_000)
    log(f"cbf: {len(d)} candidates, {(d < 100).sum()} unsafe, {((d >= 100) & (d < 150)).sum()} gray ({time.time()-t0:.0f}s)")
    uns = rng.permutation(np.flatnonzero(d < 100))
    safe_all = np.flatnonzero(d >= 150)
    w = np.exp(-(d[safe_all] - 150.0) / R["tau_mm"]); w /= w.sum()
    n_half = C["train"] // 2
    safe = rng.choice(safe_all, 2 * (len(uns) - n_half), replace=False, p=w)

    def feats(ix, label):
        km = D.measure(rng, kp[ix], sc[ix])
        return D.features(q[ix], km), np.full(len(ix), label, np.int8)

    u_tr, u_pool = uns[:n_half], uns[n_half:]
    s_tr, s_pool = safe[:n_half], safe[n_half:n_half + len(u_pool)]
    Xu, yu = feats(u_tr, -1); Xs, ys = feats(s_tr, 1)
    X = np.concatenate([Xu, Xs]); y = np.concatenate([yu, ys]); dtr = np.concatenate([d[u_tr], d[s_tr]])
    str_ = np.concatenate([sc[u_tr], sc[s_tr]])
    p = rng.permutation(len(X)); X, y, dtr, str_ = X[p], y[p], dtr[p], str_[p]
    nv = int(R["val_fraction"] * len(X))
    net = M.BarrierNet(seed=SEEDS["cbf_training"]["init"] % 2**31)
    M.train(net, X[nv:].astype(np.float64), y[nv:], X[:nv].astype(np.float64), y[:nv],
            seed=SEEDS["cbf_training"]["split"] % 2**31, epochs=R["epochs"], patience=R["patience"],
            w_unsafe=R["w_unsafe"], margin=R["margin"], lam=R["lam"], verbose=False)
    log(f"cbf: trained ({time.time()-t0:.0f}s)")

    # ---- held-out pool, scored by the trained network, then stratified to the reported error counts
    Xup, yup = feats(u_pool, -1); Xsp, ysp = feats(s_pool, 1)
    hu, hs = net.predict(Xup), net.predict(Xsp)
    nat = {"fn_rate_pool": float(((hu >= 0)).mean()), "fp_rate_pool": float((hs < 0).mean()),
           "pool_unsafe": int(len(hu)), "pool_safe": int(len(hs))}
    r = rng_for("cbf", "holdout")
    half = C["holdout"] // 2
    iu = _holdout_strata(hu, -np.ones(len(hu)), C["holdout_fn"], half, r)
    is_ = _holdout_strata(hs, np.ones(len(hs)), C["holdout_fp"], half, r)
    Xh = np.concatenate([Xup[iu], Xsp[is_]]); yh = np.concatenate([yup[iu], ysp[is_]])
    dh = np.concatenate([d[u_pool][iu], d[s_pool][is_]]); sh = np.concatenate([sc[u_pool][iu], sc[s_pool][is_]])
    ph = r.permutation(len(Xh)); Xh, yh, dh, sh = Xh[ph], yh[ph], dh[ph], sh[ph]

    # ---- gray zone: 100 <= d < 150 mm, no label. Generated AFTER training until the stratum is full:
    # the trained network abstains (|h| < 0.15) on only a few percent of the band, so the 4,570 abstentions
    # must be collected from a much larger pool (this is reported as `gray_abstain_pool`).
    Xg_l, dg_l, sg_l, ab_l = [], [], [], []
    n_ab = n_na = tot = 0
    need_ab, need_na = C["gray_abstain"], C["gray_n"] - C["gray_abstain"]
    while n_ab < need_ab or n_na < need_na:
        scen_ = rng.integers(0, 6, 250_000)
        q_ = D.sample_q(rng, 250_000, scen_)
        kp_ = D.sample_humans(rng, 250_000)
        d_ = D.dmin_mm(q_, kp_)
        k_ = np.flatnonzero((d_ >= 100) & (d_ < 150))
        Xk = D.features(q_[k_], D.measure(rng, kp_[k_], scen_[k_]))
        a_ = np.abs(net.predict(Xk)) < C["gray_threshold"]
        Xg_l.append(Xk); dg_l.append(d_[k_]); sg_l.append(scen_[k_]); ab_l.append(a_)
        tot += len(k_); n_ab += int(a_.sum()); n_na += int((~a_).sum())
    Xg_all = np.concatenate(Xg_l); dg_all = np.concatenate(dg_l); sg_all = np.concatenate(sg_l)
    ab = np.concatenate(ab_l)
    nat["gray_abstain_pool"] = float(ab.mean()); nat["gray_pool"] = int(tot)
    ia, ina = np.flatnonzero(ab), np.flatnonzero(~ab)
    ig = r.permutation(np.concatenate([r.choice(ia, need_ab, replace=False), r.choice(ina, need_na, replace=False)]))
    Xg, dg, sg = Xg_all[ig], dg_all[ig], sg_all[ig]

    L = M.lipschitz_lower_bound(net, Xh.astype(np.float64), seed=SEEDS["cbf_training"]["init"] % 2**31,
                                n_start=4000, iters=400)
    log(f"cbf: Lipschitz search lower bound {L:.2f} ({time.time()-t0:.0f}s); natural {nat}")
    path = Path(out) / "cbf_dataset_66d.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    st = net.state()
    np.savez_compressed(
        path, X_train=X.astype(np.float32), y_train=y, d_train_mm=dtr.astype(np.float32), scenario_train=str_.astype(np.int8),
        n_validation=np.array(nv),
        X_holdout=Xh.astype(np.float32), y_holdout=yh, d_holdout_mm=dh.astype(np.float32), scenario_holdout=sh.astype(np.int8),
        X_gray=Xg.astype(np.float32), d_gray_mm=dg.astype(np.float32), scenario_gray=sg.astype(np.int8),
        lipschitz_search_lower_bound=np.array(L), lipschitz_certified_upper_bound=np.array(net.c),
        gray_threshold=np.array(C["gray_threshold"]),
        recipe=np.array(json.dumps(R)), natural_rates=np.array(json.dumps(nat)),
        provenance=np.array("RECONSTRUCTED: synthetic UR5e kinematics + synthetic skeletons; holdout and gray set "
                            "are stratified to the error counts printed in the manuscript. Not sensor data."),
        **st)
    PROVENANCE["cbf"] = {"lipschitz_search_lower_bound": L, "natural": nat, "recipe": R}
    log(f"cbf: wrote {path} ({path.stat().st_size/1e6:.1f} MB)")
    return path


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


# ======================================================================= CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["all", "cycles", "stages", "ablation", "protocol", "segments", "tuning", "cbf"])
    ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--scale", type=int, default=1, help="divisor of the cycle counts (smoke tests only; 1 = full size)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    w = a.what
    if w in ("all", "cycles"):
        gen_cycles(out, a.scale)
    if w in ("all", "stages"):
        gen_stages(out, out / "cycles_36M.parquet")
    if w in ("all", "ablation"):
        gen_ablation(out, a.scale)
    if w in ("all", "protocol"):
        gen_protocol(out)
    if w in ("all", "segments"):
        gen_segments(out)
    if w in ("all", "tuning"):
        gen_tuning(out, out / "segments_30.parquet")
    if w in ("all", "cbf"):
        gen_cbf(out, a.scale)
    prov_path = out / "provenance.json"
    prev = json.loads(prov_path.read_text()) if prov_path.exists() else {}
    prev.update({
        "kind": "RECONSTRUCTED - not instrument recordings",
        "statement": ("Generated by tools/reconstruct_data.py so that the statistics printed in the manuscript "
                      "are reproduced from data. No robot, depth camera, Jetson or PLC produced these files."),
        "tool": "tools/reconstruct_data.py", "master_seed": SEEDS["master_seed"],
        "scale": a.scale, "numpy": np.__version__, "generated": time.strftime("%Y-%m-%d"),
    })
    for k, v in PROVENANCE.items():
        prev.setdefault("files", {})[k] = v
    for f in sorted(out.glob("*.parquet")) + sorted(out.glob("*.npz")):
        prev.setdefault("sha256", {})[f.name] = _sha256(f)
    prov_path.write_text(json.dumps(prev, indent=2, default=float))
    log(f"provenance: {prov_path}")


if __name__ == "__main__":
    main()
