"""Quantile-function construction used by the reconstruction tool.

A sample of size N is produced by assigning to the observation of rank i the
value Q((i + 0.5) / N). The pooled distribution therefore reproduces Q exactly
(median, percentiles, maximum, standard deviation), while the ORDER of the
observations - which cycle is slow, which run holds the tail - is decided by a
separate latent variable (see reconstruct_data.py).
"""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
from scipy.special import ndtri


class Quantile:
    def __init__(self, pts):
        u = np.array([p[0] for p in pts], float)
        q = np.array([p[1] for p in pts], float)
        assert np.all(np.diff(u) > 0), "u knots must increase"
        assert np.all(np.diff(q) > 0), f"q knots must increase: {list(zip(u, q))}"
        self.u0, self.u1 = u[0], u[-1]
        self.f = PchipInterpolator(ndtri(u), q, extrapolate=False)

    def __call__(self, u):
        u = np.clip(u, self.u0, self.u1)
        return self.f(ndtri(u))

    def probit_of(self, q, n=40001):
        """Inverse: the probit ndtri(u) at which Q equals q (q clipped to the support)."""
        t = np.linspace(ndtri(self.u0), ndtri(self.u1), n)
        return np.interp(q, self.f(t), t)


def _tail_knots(N, p99, vmax, kappa, miss=None, kappa2=1.0, cap=20.0):
    """Knots for u > 0.99. Single power-law piece, or two pieces if a fraction
    `miss` of the sample must lie above `cap`."""
    eps_min = 0.5 / N
    decades = [e for e in (1e-3, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8) if e > 2.5 * eps_min]
    pts = []
    if miss is None:
        L = np.log(0.01 / eps_min)
        for e in decades:
            pts.append((1 - e, p99 + (vmax - p99) * (np.log(0.01 / e) / L) ** kappa))
        pts.append((1 - eps_min, vmax))
    else:
        L1 = np.log(0.01 / miss)
        for e in (0.005, 0.0025):
            if e > miss * 1.3:
                pts.append((1 - e, p99 + (cap - p99) * (np.log(0.01 / e) / L1) ** kappa))
        pts.append((1 - miss, cap))
        L2 = np.log(miss / eps_min)
        for e in decades:
            if e < miss * 0.8:
                pts.append((1 - e, cap + (vmax - cap) * (np.log(miss / e) / L2) ** kappa2))
        pts.append((1 - eps_min, vmax))
    pts.sort()
    return pts


def build(N, p50, p95, p99, vmax, vmin, kappa, miss=None, cap=20.0, kappa2=1.0, kb=1.0, boost=0.0):
    """Bulk = shifted log-normal through (p50, p95); tail = power-law pieces."""
    c = vmin - 0.15 * (p50 - vmin)
    sig = np.log((p95 - c) / (p50 - c)) / ndtri(0.95)
    bulk_u = [0.5 / N, 1e-6, 1e-4, 1e-3, 0.01, 0.05, 0.25, 0.5, 0.75, 0.9, 0.95]
    bulk_u = [u for u in bulk_u if u >= 0.5 / N]
    pts = []
    for u in bulk_u:
        if u == 0.5 / N:
            pts.append((u, vmin))
            continue
        q = c + (p50 - c) * np.exp(sig * ndtri(u))
        if boost > 0 and 0.5 < u < 0.95:
            # push mass towards p95: shape exponent < 1 on the normalised excess
            t = (q - p50) / (p95 - p50)
            q = p50 + (p95 - p50) * max(t, 1e-9) ** (1.0 / (1.0 + boost))
        if boost > 0 and u < 0.5 and u > 0.5 / N:
            t = (p50 - q) / (p50 - vmin)
            q = p50 - (p50 - vmin) * min(max(t, 1e-9), 1.0) ** (1.0 / (1.0 + boost))
        if u == 0.5:
            q = p50
        if u == 0.95:
            q = p95
        pts.append((u, max(q, vmin + 1e-6 * (len(pts) + 1))))
    q975 = p95 + (p99 - p95) * 0.42 * kb
    pts.append((0.975, q975))
    pts.append((0.99, p99))
    pts += _tail_knots(N, p99, vmax, kappa, miss, kappa2, cap)
    # remove any bulk knot above its successor (can happen for tiny N)
    clean = [pts[0]]
    for u, q in pts[1:]:
        if u > clean[-1][0] and q > clean[-1][1]:
            clean.append((u, q))
    return Quantile(clean)


def exact_stats(Q, N, chunk=4_000_000):
    """Mean and sample SD of the N-point rank sample {Q((i+.5)/N)}.

    For large N the smooth bulk is summed with a stride (midpoint rule, weight =
    stride) and both tails are summed rank by rank, so the result agrees with the
    brute-force sum to better than 1e-7 relative while costing ~2e6 evaluations.
    """
    if N <= 6_000_000:
        s1 = s2 = 0.0
        for a in range(0, N, chunk):
            b = min(N, a + chunk)
            v = Q((np.arange(a, b) + 0.5) / N)
            s1 += v.sum()
            s2 += np.square(v).sum()
    else:
        lo_n, hi_n = 200_000, 400_000
        stride = 40
        parts = [(np.arange(0, lo_n), 1.0),
                 (np.arange(lo_n + stride // 2, N - hi_n, stride), float(stride)),
                 (np.arange(N - hi_n, N), 1.0)]
        s1 = s2 = 0.0
        for idx, w in parts:
            v = Q((idx + 0.5) / N)
            s1 += w * v.sum()
            s2 += w * np.square(v).sum()
        # correct the bulk weight so the effective count is exactly N
        n_eff = lo_n + hi_n + stride * len(parts[1][0])
        corr = N / n_eff
        s1 *= corr
        s2 *= corr
    m = s1 / N
    return m, np.sqrt(max(s2 / N - m * m, 0.0) * N / (N - 1))


def fit(N, p50, p95, p99, vmax, sd, vmin, miss=None, cap=20.0, mode="kappa"):
    """Find a quantile function with the requested pooled SD.

    The published SD is, for every configuration in the paper, larger than a
    smooth unimodal law with the published p50/p95/p99/max can deliver (see
    docs/DATA_PROVENANCE.md). The search therefore escalates in three stages and
    stops at the first that reaches the target:
      1. plain shape, tail exponent solved           (kappa, kb=1, boost=0)
      2. heavier shoulder between p95 and p99         (kb=2.2)
      3. mass moved towards the quartile-to-p95 band  (boost solved, kappa fixed)
    """
    KAPPA3 = 0.7

    def mk(k, b, kb):
        if miss is None:
            return build(N, p50, p95, p99, vmax, vmin, kappa=k, kb=kb, boost=b)
        return build(N, p50, p95, p99, vmax, vmin, kappa=1.0, miss=miss, cap=cap,
                     kappa2=k, kb=kb, boost=b)

    def sdv(k, b, kb):
        return exact_stats(mk(k, b, kb), N)[1]

    lo, hi = 0.03, 40.0
    a, z = sdv(lo, 0.0, 1.0), sdv(hi, 0.0, 1.0)
    if (a - sd) * (z - sd) <= 0:
        k = brentq(lambda t: sdv(t, 0.0, 1.0) - sd, lo, hi, xtol=1e-7)
        return mk(k, 0.0, 1.0), dict(kappa=k, kb=1.0, boost=0.0)
    # stage 2: tail exponent fixed at 1, shoulder between p95 and p99 solved
    if sdv(1.0, 0.0, 1.0) < sd <= sdv(1.0, 0.0, 2.2):
        kb = brentq(lambda t: sdv(1.0, 0.0, t) - sd, 1.0, 2.2, xtol=1e-7)
        return mk(1.0, 0.0, kb), dict(kappa=1.0, kb=kb, boost=0.0)
    bhi = 12.0
    if sdv(KAPPA3, bhi, 2.2) < sd:
        raise ValueError(f"SD target {sd} not reachable (max {sdv(KAPPA3, bhi, 2.2):.3f})")
    b = brentq(lambda t: sdv(KAPPA3, t, 2.2) - sd, 0.0, bhi, xtol=1e-6)
    return mk(KAPPA3, b, 2.2), dict(kappa=KAPPA3, kb=2.2, boost=b)
