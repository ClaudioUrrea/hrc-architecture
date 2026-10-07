"""Synthetic data for the 66-dimensional barrier network (Section 7.2).

State = 6 joint angles of a UR5e + 20 human skeleton keypoints (Cartesian, m).
The label comes from the TRUE minimum separation between robot link points and
human keypoints; the network sees a noisy measurement of the keypoints (stationary
depth-camera noise; in scenario S4 a share of keypoints is occluded and replaced by
a default position), which is what makes the classification problem non-trivial.

Everything here is a reconstruction: no depth camera, robot or person produced it.
"""
import numpy as np

# UR5e DH parameters (Universal Robots, e-Series)
DH_D = np.array([0.1625, 0.0, 0.0, 0.1333, 0.0997, 0.0996])
DH_A = np.array([0.0, -0.425, -0.3922, 0.0, 0.0, 0.0])
DH_ALPHA = np.array([np.pi / 2, 0.0, 0.0, np.pi / 2, -np.pi / 2, 0.0])

SCENARIOS = ["S1", "S2", "S3", "S4", "S5", "S6"]
# keypoint noise (m, std) and occlusion probability per scenario
NOISE_SD = 0.8 * np.array([0.012, 0.014, 0.016, 0.020, 0.017, 0.013])
OCCLUSION = np.array([0.00, 0.00, 0.00, 0.20, 0.00, 0.00])
DEFAULT_KP = None   # set lazily: mean keypoint pose


def fk_points(q):
    """Positions (B, 11, 3) of the six joint frames and five link midpoints."""
    B = q.shape[0]
    T = np.tile(np.eye(4), (B, 1, 1))
    pts = [T[:, :3, 3].copy()]
    prev = pts[0]
    out = []
    for i in range(6):
        ct, st = np.cos(q[:, i]), np.sin(q[:, i])
        ca, sa = np.cos(DH_ALPHA[i]), np.sin(DH_ALPHA[i])
        A = np.zeros((B, 4, 4))
        A[:, 0, 0] = ct; A[:, 0, 1] = -st * ca; A[:, 0, 2] = st * sa; A[:, 0, 3] = DH_A[i] * ct
        A[:, 1, 0] = st; A[:, 1, 1] = ct * ca; A[:, 1, 2] = -ct * sa; A[:, 1, 3] = DH_A[i] * st
        A[:, 2, 1] = sa; A[:, 2, 2] = ca; A[:, 2, 3] = DH_D[i]
        A[:, 3, 3] = 1.0
        T = T @ A
        p = T[:, :3, 3].copy()
        out.append((prev + p) / 2)
        out.append(p)
        prev = p
    P = np.stack(out, axis=1)          # (B, 12, 3): midpoint and end of each of the six links
    return P[:, 1:, :]                 # drop the degenerate first midpoint -> 11 points


_Q_HOME = np.array([0.0, -1.57, 1.57, -1.57, -1.57, 0.0])
_TRAJ = np.random.default_rng(20291552)           # fixed: the six task paths are part of the data set
_TRAJ_A = _TRAJ.uniform(0.25, 0.65, (6, 6, 2))     # scenario, joint, harmonic
_TRAJ_P = _TRAJ.uniform(0, 2 * np.pi, (6, 6, 2))


def sample_q(rng, n, scen=None):
    """Joint vector along the (smooth, closed) task path of the scenario, plus a small deviation."""
    if scen is None:
        scen = rng.integers(0, 6, n)
    phi = rng.random(n)
    q = np.tile(_Q_HOME, (n, 1))
    for k in (0, 1):
        q = q + _TRAJ_A[scen, :, k] * np.sin(2 * np.pi * (k + 1) * phi[:, None] + _TRAJ_P[scen, :, k])
    return q + rng.normal(0, 0.06, (n, 6))


# keypoint order: head, neck, spine, pelvis, Lsh, Rsh, Lel, Rel, Lwr, Rwr, Lhand, Rhand,
#                 Lhip, Rhip, Lknee, Rknee, Lank, Rank, Lfoot, Rfoot
_TEMPLATE = np.array([
    [0, 0, 1.65], [0, 0, 1.50], [0, 0, 1.25], [0, 0, 0.95],
    [-0.20, 0, 1.45], [0.20, 0, 1.45], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0],
    [-0.10, 0, 0.92], [0.10, 0, 0.92], [-0.10, 0, 0.50], [0.10, 0, 0.50],
    [-0.10, 0, 0.08], [0.10, 0, 0.08], [-0.10, 0.12, 0.02], [0.10, 0.12, 0.02]])


def sample_humans(rng, n, rmin=0.45, rmax=1.35):
    """(n, 20, 3) keypoints in the robot base frame (z up)."""
    kp = np.tile(_TEMPLATE, (n, 1, 1))
    lean = rng.normal(0, 0.12, n)
    kp[:, 0:3, 1] += (kp[:, 0:3, 2] - 0.95)[:, :] * np.sin(lean)[:, None]       # forward lean
    for side, (sh, el, wr, hd) in enumerate([(4, 6, 8, 10), (5, 7, 9, 11)]):
        d1 = rng.normal(size=(n, 3)); d1[:, 2] -= 0.8; d1 /= np.linalg.norm(d1, axis=1, keepdims=True)
        d2 = d1 + 0.9 * rng.normal(size=(n, 3)); d2 /= np.linalg.norm(d2, axis=1, keepdims=True)
        # reaching bias: forward (+y) component
        d1[:, 1] += 0.5; d2[:, 1] += 0.7
        d1 /= np.linalg.norm(d1, axis=1, keepdims=True); d2 /= np.linalg.norm(d2, axis=1, keepdims=True)
        kp[:, el] = kp[:, sh] + 0.29 * d1
        kp[:, wr] = kp[:, el] + 0.26 * d2
        kp[:, hd] = kp[:, wr] + 0.09 * d2
    for k in (14, 15, 16, 17, 18, 19):
        kp[:, k, :2] += rng.normal(0, 0.03, (n, 2))
    r = rng.uniform(rmin, rmax, n)
    th = rng.uniform(-np.pi, np.pi, n)
    # the person faces the robot (their +y points at the base) with a spread of 0.7 rad
    yaw = th + np.pi / 2 + np.pi + rng.normal(0, 0.7, n)
    cy, sy = np.cos(yaw), np.sin(yaw)
    x = kp[:, :, 0] * cy[:, None] - kp[:, :, 1] * sy[:, None]
    y = kp[:, :, 0] * sy[:, None] + kp[:, :, 1] * cy[:, None]
    kp[:, :, 0], kp[:, :, 1] = x, y
    kp[:, :, 0] += (r * np.cos(th))[:, None]
    kp[:, :, 1] += (r * np.sin(th))[:, None]
    return kp


def dmin_mm(q, kp):
    P = fk_points(q)                                        # (B, 11, 3)
    d = np.linalg.norm(P[:, :, None, :] - kp[:, None, :, :], axis=3)
    return 1000.0 * d.min(axis=(1, 2))


def candidates(rng, n_target, chunk=250_000):
    """Draw (q, kp, dmin, scenario) until at least n_target candidates of the unsafe class exist."""
    Q, K, D, S = [], [], [], []
    n_unsafe = 0
    while n_unsafe < n_target:
        scen = rng.integers(0, 6, chunk)
        q = sample_q(rng, chunk, scen)
        kp = sample_humans(rng, chunk)
        d = dmin_mm(q, kp)
        keep = d < 600.0
        Q.append(q[keep]); K.append(kp[keep]); D.append(d[keep]); S.append(scen[keep])
        n_unsafe += int((d < 100.0).sum())
    return np.concatenate(Q), np.concatenate(K), np.concatenate(D), np.concatenate(S)


def measure(rng, kp, scen):
    """Noisy, partly occluded measurement of the keypoints."""
    global DEFAULT_KP
    if DEFAULT_KP is None:
        DEFAULT_KP = kp.mean(axis=0)
    noisy = kp + rng.normal(size=kp.shape) * NOISE_SD[scen][:, None, None]
    occ = rng.random(kp.shape[:2]) < OCCLUSION[scen][:, None]
    noisy[occ] = np.broadcast_to(DEFAULT_KP, kp.shape)[occ]
    return noisy


def features(q, kp_meas):
    return np.concatenate([q, kp_meas.reshape(len(q), -1)], axis=1)
