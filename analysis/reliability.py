"""Reliability analysis within the 200 h observation window (Section 9.5, Figure 10).

The 847 h MTBF extrapolation of the first submission is WITHDRAWN: it is not
derivable from a 200 h observation of a population whose observed MTBF is of the
order of one hour. Nothing here is extrapolated beyond the window.

v2.0.0 (round 2). RIGHT-CENSORING IS NOW HANDLED, NOT DISCARDED.

The campaign is time-truncated: observation stops at T = 200 h, not at a
failure. The 156 service-affecting events therefore yield 155 complete
inter-failure intervals plus one incomplete interval, from the last event to the
end of the run, whose true length is known only to exceed the elapsed 0.42 h.
That interval is the LONGEST observation in the sequence, so dropping it - as
v1.0.0 did - discards information and biases the scale downward.

The reported fit maximizes the Type-I censored log-likelihood

    l(beta, eta) = sum_i log f(t_i; beta, eta) + log S(t_c; beta, eta)

over the 155 complete intervals plus the survival term for the censored one, so
the censored observation contributes the probability that the interval exceeds
t_c rather than a density at a value it does not have. The uncensored fit is
reported alongside as a sensitivity, because a reader is entitled to know
whether the choice matters: it moves the shape from 1.02 to 1.04 and the scale
from 1.26 to 1.25 h, both inside the bootstrap interval.

The bootstrap resamples the 156 observations as a unit, so the censored point is
resampled with its censoring indicator intact. The exact Poisson intervals are
unaffected: a count over a fixed window is not censored at all.
"""
import argparse, json
import numpy as np
from scipy import optimize, stats

T = 200.0                       # exposure, hours
POPULATIONS = {"all_faults": 166, "service_affecting": 156, "operator_intervention": 6}


def poisson_ci(k, T, alpha=0.05):
    """Exact (Garwood) interval for a Poisson rate."""
    lo = stats.chi2.ppf(alpha / 2, 2 * k) / 2 / T if k > 0 else 0.0
    hi = stats.chi2.ppf(1 - alpha / 2, 2 * k + 2) / 2 / T
    return lo, hi


def _neg_loglik(params, complete, censored):
    """Type-I right-censored Weibull negative log-likelihood (location fixed at 0).

    `complete` are fully observed intervals; `censored` are lower bounds, each
    contributing log S(t) = -(t/eta)**beta.
    """
    log_beta, log_eta = params
    beta, eta = np.exp(log_beta), np.exp(log_eta)
    ll = np.sum(stats.weibull_min.logpdf(complete, beta, 0.0, eta))
    if censored.size:
        ll += np.sum(stats.weibull_min.logsf(censored, beta, 0.0, eta))
    return -ll


def weibull_fit_censored(complete, censored, n_boot=2000, seed=20260908):
    """MLE with the censored observations entering through the survival term."""
    beta0, _loc, eta0 = stats.weibull_min.fit(complete, floc=0)
    res = optimize.minimize(_neg_loglik, x0=[np.log(beta0), np.log(eta0)],
                            args=(complete, censored), method="Nelder-Mead",
                            options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": 4000})
    beta, eta = np.exp(res.x)

    # Goodness of fit is assessed on the complete intervals only: the censored
    # point has no realized value to compare against an EDF.
    ks = stats.kstest(complete, "weibull_min", args=(beta, 0, eta))

    # Resample the observations as a unit, censoring indicator intact.
    rng = np.random.default_rng(seed)
    obs = np.concatenate([complete, censored])
    flag = np.concatenate([np.zeros(complete.size, bool), np.ones(censored.size, bool)])
    boot = []
    for _ in range(n_boot):
        idx = rng.integers(0, obs.size, obs.size)
        c, z = obs[idx][~flag[idx]], obs[idx][flag[idx]]
        if c.size < 10:
            continue
        b0, _l, e0 = stats.weibull_min.fit(c, floc=0)
        r = optimize.minimize(_neg_loglik, x0=[np.log(b0), np.log(e0)], args=(c, z),
                              method="Nelder-Mead", options={"maxiter": 2000})
        boot.append(np.exp(r.x[0]))
    lo, hi = np.percentile(boot, [2.5, 97.5])

    # Sensitivity: the fit the previous version reported, with the censored
    # observation dropped entirely.
    b_u, _l, e_u = stats.weibull_min.fit(complete, floc=0)

    return {"shape": float(beta), "shape_ci95": [float(lo), float(hi)],
            "scale_h": float(eta), "ks_p": float(ks.pvalue),
            "censoring": {"type": "Type-I right, time-truncated at 200 h",
                          "n_complete": int(complete.size),
                          "n_censored": int(censored.size),
                          "t_censored_h": float(censored[0]) if censored.size else None,
                          "treatment": "survival term in the log-likelihood"},
            "sensitivity_censored_point_dropped": {"shape": float(b_u),
                                                   "scale_h": float(e_u)}}


def main(interfailure_csv="data/interfailure.csv"):
    intervals = np.loadtxt(interfailure_csv, delimiter=",", skiprows=1, usecols=1)
    complete, censored = intervals[:-1], intervals[-1:]
    out = {"exposure_h": T,
           "weibull": weibull_fit_censored(complete, censored),
           "populations": {}}
    for name, k in POPULATIONS.items():
        lo, hi = poisson_ci(k, T)
        out["populations"][name] = {
            "events": k, "rate_per_h": k / T, "rate_ci95": [lo, hi],
            "mtbf_h": T / k, "mtbf_ci95": [1 / hi, (1 / lo) if lo > 0 else None]}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/interfailure.csv")
    print(json.dumps(main(ap.parse_args().data), indent=2))
