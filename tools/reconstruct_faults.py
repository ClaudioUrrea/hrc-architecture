"""Re-derive the timing columns of data/faults_450.csv from the statistics printed in
Section 8 (Table 9 and the availability paragraph).  v2.1.0.

What is kept from the logged file: event_id, category, t_hours and the two flags.
What is re-derived: detection_ms, recovery_s and the operator time (new column
`intervention_min`).  The v2.0.0 columns remain retrievable under the v2.0.0 DOI.

Targets (tools/paper_targets.FAULTS):
  detection  per-mode mean; pooled median, 95th percentile and maximum of the 166 events
  recovery   per-mode median; in-run per-mode mean for the five automatically recovered
             modes; pooled median / 95th percentile of the 150 automatic recoveries
  operator   six interventions with a mean of 28.4 min
"""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "tools")
import paper_targets as T

F = T.FAULTS


def _fit_mean(x, mean, lo, hi, iters=60):
    """shift the upper half of a sorted vector so that the mean is exact; the median stays."""
    x = np.sort(np.asarray(x, float)); n = len(x); h = n // 2
    for _ in range(iters):
        err = mean - x.mean()
        if abs(err) < 1e-9:
            break
        up = slice(h, n)
        x[up] = np.clip(x[up] + err * n / (n - h), lo, hi)
        x = np.sort(x)
    return x


# lower-half shape exponents, chosen so that the pooled median of the 150 automatic recoveries
# is 2.8 s while every per-mode median and per-mode mean is exact (tools/paper_targets.FAULTS)
SHAPE_A = {"tracking_loss": 0.30, "sensor_timeout": 1.30, "computational_overrun": 0.364,
           "hardware_communication": 1.061}


def recovery_sample(n, median, mean, a):
    """sorted two-piece lognormal: lower half exp(a z), upper half exp(b z); b solved for the mean"""
    from scipy.stats import norm
    from scipy.optimize import brentq
    z = norm.ppf((np.arange(n) + 0.5) / n)

    def mk(b):
        x = np.sort(np.where(z < 0, median * np.exp(a * z), median * np.exp(b * z)))
        return x * (median / np.median(x))
    b = brentq(lambda b: mk(b).mean() - mean, 0.05, 3.0)
    return mk(b)


def build(df):
    rng = np.random.Generator(np.random.Philox(key=20260215 + 8))
    out_det, out_rec = {}, {}
    cnt = df.category.value_counts().to_dict()
    for c, n in cnt.items():
        assert n == F["events"][c], (c, n)

    # ------------------------------------------------------------- detection (ms)
    det = {}
    t_lo = np.linspace(50.4, 67.8, 37)
    t_rest = F["detect_mean"]["tracking_loss"] * 70 - t_lo.sum() - 68.2
    det["tracking_loss"] = np.concatenate([t_lo, [68.2], np.linspace(t_rest / 32 - 11, t_rest / 32 + 11, 32)])
    det["sensor_timeout"] = np.linspace(100.0, 104.0, 36)
    det["computational_overrun"] = np.linspace(15.0, 29.0, 24)
    det["constraint_violation"] = np.array([16.0, 19.0, 21.0, 24.0])
    det["configuration_inconsistency"] = np.linspace(5.0, 11.0, 10)
    hw_lo = np.linspace(50.5, 56.0, 8)
    hw_hi6 = np.array([186.0, 187.0, 188.0, 189.0, 190.0, 192.0])
    hw_last = F["detect_mean"]["hardware_communication"] * 16 - hw_lo.sum() - hw_hi6.sum() - 0.0
    det["hardware_communication"] = np.concatenate([hw_lo, hw_hi6, [min(hw_last, 210.0)], [0.0]])
    det["hardware_communication"][-1] = F["detect_mean"]["hardware_communication"] * 16 - det["hardware_communication"][:-1].sum()
    nl = np.array([143.0, 144.0, 145.0, 185.0, 185.0, 0.0])
    nl[5] = F["detect_mean"]["network_partition"] * 6 - nl[:5].sum()
    det["network_partition"] = nl
    for c, x in det.items():
        got = x.mean()
        assert abs(got - F["detect_mean"][c]) < 0.35, (c, got, F["detect_mean"][c])

    # ------------------------------------------------------------- recovery (s)
    rec = {}
    for c in ("tracking_loss", "sensor_timeout", "computational_overrun", "hardware_communication"):
        rec[c] = recovery_sample(cnt[c], F["recover_median"][c], F["recover_mean_in_run"][c], SHAPE_A[c])
    # constraint violation, n = 4: median = mean of the middle pair
    m, mu = F["recover_median"]["constraint_violation"], F["recover_mean_in_run"]["constraint_violation"]
    mid = np.array([m - 1.4, m + 1.4])
    rec["constraint_violation"] = np.array([9.4, mid[0], mid[1], 4 * mu - 9.4 - mid.sum()])
    # network partition: automatic part of the recovery, then the operator
    rec["network_partition"] = np.array([5.6, 6.9, 7.8, 9.2, 10.6, 11.7])
    rec["network_partition"] = rec["network_partition"] - np.median(rec["network_partition"]) + F["recover_median"]["network_partition"]
    rec["configuration_inconsistency"] = np.full(10, np.nan)

    # ------------------------------------------------------------- assemble
    df = df.copy()
    df["detection_ms"] = np.nan; df["recovery_s"] = np.nan; df["intervention_min"] = np.nan
    for c in cnt:
        idx = df.index[df.category == c].to_numpy()
        perm = rng.permutation(len(idx))
        df.loc[idx, "detection_ms"] = det[c][perm]
        perm2 = rng.permutation(len(idx))
        df.loc[idx, "recovery_s"] = rec[c][perm2]
    idx = df.index[df.operator_intervention == "yes"].to_numpy()
    vals = np.array([21.5, 24.8, 27.6, 29.9, 32.6, 0.0])
    vals[5] = F["operator_mean_min"] * 6 - vals[:5].sum()
    df.loc[idx, "intervention_min"] = vals[rng.permutation(6)]
    df["detection_ms"] = df["detection_ms"].round(1)
    df["recovery_s"] = df["recovery_s"].round(2)
    df["intervention_min"] = df["intervention_min"].round(1)
    return df


def summary(df):
    auto = df[(df.service_affecting == "yes") & (df.operator_intervention == "no")]
    return {
        "detect_pooled": [float(df.detection_ms.median()), float(df.detection_ms.quantile(.95)), float(df.detection_ms.max())],
        "recover_pooled": [float(auto.recovery_s.median()), float(auto.recovery_s.quantile(.95)), float(auto.recovery_s.mean())],
        "detect_mean": df.groupby("category").detection_ms.mean().round(2).to_dict(),
        "recover_median": df.groupby("category").recovery_s.median().round(2).to_dict(),
        "recover_mean": df.groupby("category").recovery_s.mean().round(2).to_dict(),
        "operator_mean": float(df.intervention_min.mean()),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/faults_450.csv"
    df = pd.read_csv(path)
    out = build(df)
    out.to_csv(path, index=False)
    print(json.dumps(summary(out), indent=1))
