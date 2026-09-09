"""Reliability analysis within the 200 h observation window (Section 9.5, Figure 10).

The 847 h MTBF extrapolation of the first submission is WITHDRAWN: it is not
derivable from a 200 h observation of a population whose observed MTBF is of the
order of one hour. Nothing here is extrapolated beyond the window.
"""
import argparse, json
import numpy as np
from scipy import stats

T = 200.0                       # exposure, hours
POPULATIONS = {"all_faults": 166, "service_affecting": 156, "operator_intervention": 6}


def poisson_ci(k, T, alpha=0.05):
    """Exact (Garwood) interval for a Poisson rate."""
    lo = stats.chi2.ppf(alpha / 2, 2 * k) / 2 / T if k > 0 else 0.0
    hi = stats.chi2.ppf(1 - alpha / 2, 2 * k + 2) / 2 / T
    return lo, hi


def weibull_fit(intervals, n_boot=2000, seed=20260908):
    """MLE with the location fixed at zero, bootstrap CI on the shape, KS check.

    The final interval of the sequence is right-censored by the end of the run and
    is dropped from the likelihood; the Poisson intervals use the full exposure and
    are unaffected.
    """
    beta, _loc, eta = stats.weibull_min.fit(intervals, floc=0)
    ks = stats.kstest(intervals, "weibull_min", args=(beta, 0, eta))
    rng = np.random.default_rng(seed)
    boot = np.array([stats.weibull_min.fit(rng.choice(intervals, intervals.size, replace=True),
                                           floc=0)[0] for _ in range(n_boot)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"shape": beta, "shape_ci95": [lo, hi], "scale_h": eta, "ks_p": ks.pvalue}


def main(interfailure_csv):
    intervals = np.loadtxt(interfailure_csv, delimiter=",", skiprows=1, usecols=1)
    out = {"exposure_h": T, "weibull": weibull_fit(intervals[:-1]), "populations": {}}
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
