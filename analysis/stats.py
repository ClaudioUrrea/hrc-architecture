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


# ---------------------------------------------------------------- release 3.1 (Reviewer 2, round 4)
def run_bootstrap_rate(counts, exposures, n_boot=10000, alpha=0.05, seed=0):
    """Rate = sum(counts)/sum(exposures) with a percentile interval from resampling whole runs.

    Runs are the independent units (each starts cold); events inside a run may be clustered,
    which the exact Poisson interval ignores and this interval does not."""
    k = np.asarray(counts, float)
    e = np.asarray(exposures, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(k), (n_boot, len(k)))
    rates = k[idx].sum(1) / e[idx].sum(1)
    return float(k.sum() / e.sum()), [float(np.quantile(rates, alpha / 2)), float(np.quantile(rates, 1 - alpha / 2))]


def dispersion_index(counts, exposures):
    """Pearson dispersion of per-run counts around a common rate (about 1 under a Poisson process,
    > 1 with clustering or run-to-run variation), with its chi-square p-value (H0: Poisson)."""
    k = np.asarray(counts, float)
    e = np.asarray(exposures, float)
    if len(k) < 2 or k.sum() == 0:
        return {"index": None, "p_overdispersion": None}
    mu = e * k.sum() / e.sum()
    x2 = float(np.sum((k - mu) ** 2 / mu))
    df = len(k) - 1
    return {"index": x2 / df, "chi2": x2, "df": df, "p_overdispersion": float(stats.chi2.sf(x2, df))}


def _simulate_weibull_runs(durations, k, lam, rng):
    t, cz = [], []
    for dur in durations:
        s = 0.0
        while True:
            x = lam * rng.weibull(k)
            if s + x > dur:
                t.append(dur - s); cz.append(True)
                break
            s += x
            t.append(x); cz.append(False)
    return np.array(t), np.array(cz)


def weibull_param_bootstrap(durations, k, lam, ks_obs, n_boot=1000, seed=0):
    """Calibrated goodness of fit for a Weibull renewal model fitted with censoring.

    Reproduces the observation process (each run starts cold, renewal intervals until the run
    ends, last interval right-censored), refits by censored MLE in every replicate and computes
    the KS statistic on the complete intervals against the refitted model. p = share of
    replicates with a statistic >= the observed one. This accounts for fitting the parameters
    from the same data and for the censoring scheme, which the plain KS p-value does not."""
    rng = np.random.default_rng(seed)
    ge, done = 0, 0
    for _ in range(n_boot):
        t, cz = _simulate_weibull_runs(durations, k, lam, rng)
        if (~cz).sum() < 5:
            continue
        kb, lb = weibull_mle(t, cz)
        if weibull_ks(t[~cz], kb, lb).statistic >= ks_obs:
            ge += 1
        done += 1
    return {"replicates": done, "p_value": (ge + 1) / (done + 1) if done else None}
