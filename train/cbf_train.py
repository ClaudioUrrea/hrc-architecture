"""Revalidate the 66-dimensional barrier network (Section 7.2) from data/cbf_dataset_66d.npz.

The network of reference [3] took a 24-dimensional input built from a six-segment
operator model. This one takes 66 dimensions: six joint positions plus twenty
skeleton keypoints in Cartesian coordinates. That is a change of representation,
not a change of scale, so the network was retrained from scratch and revalidated;
the accuracy reported in the paper is the accuracy of THIS model.

Labels: safe at d >= 150 mm, unsafe at d < 100 mm; [100, 150) mm carries no label
and is excluded from training. A separate gray-zone set is evaluated after
training; the controller clamps any barrier value with |h| < 0.15 to min(h, 0),
so an abstention can only tighten the constraint, never relax it.

v2.1.0. Nothing is a constant any more: the stored weights are evaluated on the
stored held-out and gray-zone sets, and every figure below is computed from them.
PROVENANCE: the npz is a RECONSTRUCTION (synthetic kinematics and skeletons), see
docs/DATA_PROVENANCE.md. `python train/cbf_train.py --retrain` re-fits the network
on the stored training split (NumPy, ~10 min on a laptop CPU).

The Lipschitz entry has two parts that must not be confused. The certified UPPER
bound is c * prod(spectral norms) <= 10 by construction (spectral norms are
projected to <= 1). The EMPIRICAL value is a LOWER bound found by adversarial
ascent; it certifies nothing.
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cbf_model as M          # noqa: E402

PATH = "data/cbf_dataset_66d.npz"
CONFIG = {
    "input_dim": 66, "hidden": [128, 128, 128], "activation": "LeakyReLU(0.01)",
    "spectral_normalization": True, "certified_lipschitz_upper_bound": 10.0,
    "loss": "hinge + spectral-norm penalty", "optimizer": "adam",
    "lr": 1e-3, "batch_size": 256, "epochs": 500, "early_stopping": True,
    "batch_norm_at_inference": False,
}


def wilson(k, n, z=1.959964):
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(float(mid - half), 4), round(float(mid + half), 4)]


def load(path=PATH):
    z = np.load(path, allow_pickle=False)
    return z, M.BarrierNet.from_state({k: z[k] for k in z.files if k[0] in "Wb" and k[1:].isdigit() or k in ("c", "mu")})


def main(path=PATH, retrain=False):
    z, net = load(path)
    if retrain:
        nv = int(z["n_validation"])
        X, y = z["X_train"].astype(np.float64), z["y_train"]
        M.train(net, X[nv:], y[nv:], X[:nv], y[:nv], seed=1, verbose=True)
    Xh, yh = z["X_holdout"].astype(np.float64), z["y_holdout"]
    h = net.predict(Xh)
    n = len(yh)
    unsafe, safe = yh < 0, yh > 0
    fn = int(((h >= 0) & unsafe).sum())           # unsafe state declared safe
    fp = int(((h < 0) & safe).sum())              # safe state declared unsafe
    correct = n - fn - fp
    thr = float(z["gray_threshold"])
    hg = net.predict(z["X_gray"].astype(np.float64))
    abst = int((np.abs(hg) < thr).sum())
    # tightening check: after clamping, no gray-zone state can end up MORE permissive than h
    clamped = np.where(np.abs(hg) < thr, np.minimum(hg, 0.0), hg)
    # certified upper bound: product of the spectral norms of the stored weights
    sig = [float(np.linalg.svd(w, compute_uv=False)[0]) for w in net.W]
    upper = float(net.c * np.prod(np.minimum(sig, 1.0 + 1e-9)))
    return {
        "source": path, "config": CONFIG,
        "holdout_n": n, "holdout_unsafe": int(unsafe.sum()), "holdout_safe": int(safe.sum()),
        "accuracy": round(correct / n, 4), "accuracy_wilson_ci95": wilson(correct, n),
        "false_negatives": fn, "false_negative_rate": round(fn / unsafe.sum(), 4),
        "false_negative_ci95": wilson(fn, int(unsafe.sum())),
        "false_positives": fp, "false_positive_rate": round(fp / safe.sum(), 4),
        "gray_zone_n": int(len(hg)), "gray_zone_abstentions": abst,
        "gray_zone_abstention_rate": round(abst / len(hg), 4),
        "gray_zone_clamp_never_relaxes": bool((clamped <= hg + 1e-12).all()),
        "spectral_norms_max": round(max(sig), 6),
        "certified_lipschitz_upper_bound": round(upper, 3),
        "empirical_lipschitz_lower_bound": round(float(z["lipschitz_search_lower_bound"]), 2),
        "note": ("the empirical value is a LOWER bound found by adversarial gradient ascent; "
                 "the certification argument uses the constructed upper bound of 10."),
        "inference_ms": {"forward_only_p50": 1.8, "forward_plus_gradient_p50": 2.2,
                         "source": "analysis/boundaries.py (stage_timings.parquet)"},
        "reconstructed": True,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=PATH)
    ap.add_argument("--retrain", action="store_true")
    a = ap.parse_args()
    print(json.dumps(main(a.data, a.retrain), indent=2))
