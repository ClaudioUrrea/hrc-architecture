"""Statistical helpers used by the analysis scripts (numpy + scipy only)."""
import numpy as np
from scipy import optimize, stats


def bca_ci(x, stat=np.mean, n_boot=10000, alpha=0.05, seed=0):
    """Bias-corrected and accelerated bootstrap interval of stat(x)."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    theta = stat(x)
    boots = np.array([stat(x[rng.integers(0, len(x), len(x))]) for _ in range(n_boot)])
    z0 = stats.norm.ppf(np.clip(np.mean(boots < theta), 1e-6, 1 - 1e-6))
    jack = np.array([stat(np.delete(x, i)) for i in range(len(x))])
    jm = jack.mean()
    num = np.sum((jm - jack) ** 3)
    den = 6 * np.sum((jm - jack) ** 2) ** 1.5
    acc = num / den if den > 0 else 0.0
    zs = stats.norm.ppf([alpha / 2, 1 - alpha / 2])
    adj = stats.norm.cdf(z0 + (z0 + zs) / (1 - acc * (z0 + zs)))
    return float(theta), [float(np.quantile(boots, adj[0])), float(np.quantile(boots, adj[1]))]


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj


def paired(a, b):
    """Paired comparison a - b: mean, BCa CI, d_z, two-sided paired t p-value."""
    d = np.asarray(a, float) - np.asarray(b, float)
    mean, ci = bca_ci(d)
    sd = d.std(ddof=1)
    t = stats.ttest_rel(a, b)
    return {"n": int(len(d)), "mean_diff": mean, "ci95": ci, "d_z": float(mean / sd) if sd > 0 else None,
            "t": float(t.statistic), "p": float(t.pvalue)}


def poisson_rate_ci(k, exposure, alpha=0.05):
    lo = stats.chi2.ppf(alpha / 2, 2 * k) / 2 / exposure if k > 0 else 0.0
    hi = stats.chi2.ppf(1 - alpha / 2, 2 * k + 2) / 2 / exposure
    return [float(lo), float(hi)]


def zero_events_upper(n, alpha=0.05):
    """Exact one-sided upper bound on a probability after 0 events in n independent trials."""
    return float(1 - alpha ** (1.0 / n)) if n > 0 else None


def weibull_mle(t, censored):
    """Weibull MLE with right censoring. t: durations, censored: bool array (True = censored)."""
    t = np.asarray(t, float)
    c = np.asarray(censored, bool)
    obs = ~c

    def nll(p):
        k, lam = np.exp(p)
        z = t / lam
        ll = np.sum(obs * (np.log(k / lam) + (k - 1) * np.log(z))) - np.sum(z ** k)
        return -ll

    r = optimize.minimize(nll, [0.0, np.log(np.mean(t))], method="Nelder-Mead", options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 5000})
    k, lam = np.exp(r.x)
    return float(k), float(lam)


def weibull_ks(t_obs, k, lam):
    return stats.kstest(t_obs, lambda x: 1 - np.exp(-(np.asarray(x) / lam) ** k))
