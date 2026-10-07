"""Shared statistical helpers used by both the analysis scripts and the
data-reconstruction tool, so that the two cannot drift apart.

Everything here is implemented with NumPy/SciPy primitives only, so results do
not depend on the version-specific signature of scipy.stats.bootstrap.
"""
import numpy as np
from scipy.special import ndtr, ndtri


def bca_ci(x, n_boot=10_000, alpha=0.05, seed=0):
    """Bias-corrected and accelerated bootstrap interval for the MEAN of x.

    x is a short vector (the 30 run-level medians of a configuration, or the 30
    paired segment differences). Resampling is deterministic given `seed`.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    theta = x.mean()
    rng = np.random.default_rng(seed)
    boots = x[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    prop = np.mean(boots < theta) + 0.5 * np.mean(boots == theta)
    z0 = ndtri(min(max(prop, 1e-6), 1 - 1e-6))
    jack = (x.sum() - x) / (n - 1)
    d = jack.mean() - jack
    denom = 6.0 * (np.sum(d ** 2) ** 1.5)
    a = np.sum(d ** 3) / denom if denom > 0 else 0.0
    out = []
    for z in (ndtri(alpha / 2), ndtri(1 - alpha / 2)):
        out.append(ndtr(z0 + (z0 + z) / (1 - a * (z0 + z))))
    lo, hi = np.quantile(boots, out)
    return float(lo), float(hi)


def holm(pvals):
    """Holm step-down adjusted p-values."""
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    m = p.size
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj


def wilson(k, n, z=1.959963984540054):
    """Wilson score interval for a binomial proportion."""
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return float(c - h), float(c + h)


def histogram_quantiles(counts, step, qs, offset=0.0):
    """Exact quantiles from an integer histogram of values quantized to `step`.

    counts[i] is the number of observations equal to offset + i*step. The
    quantile definition is the lower empirical one: smallest value whose
    cumulative share is >= q.
    """
    cum = np.cumsum(counts)
    total = cum[-1]
    out = []
    for q in qs:
        i = int(np.searchsorted(cum, q * total, side="left"))
        out.append(offset + i * step)
    return out
