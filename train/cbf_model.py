"""Lipschitz-constrained barrier network, NumPy implementation.

h(x) = c * ( W4 a3 + b4 ),  a_l = LeakyReLU(W_l a_{l-1} + b_l, 0.01),  x in R^66.
Every weight matrix is held at spectral norm <= 1 (power iteration while training,
exact SVD projection at the end), LeakyReLU is 1-Lipschitz, so  Lip(h) <= c  by
construction. c = 10 is the certified upper bound used in the paper.

NumPy rather than PyTorch so that the training set can be regenerated and the
network retrained on a machine without a deep-learning stack; the architecture,
loss (hinge + spectral-norm penalty), optimizer (Adam, 1e-3, batch 256) and
early stopping follow cfg/cbf_train.yaml.
"""
import numpy as np

ALPHA = 0.01


def leaky(z):
    return np.where(z > 0, z, ALPHA * z)


def dleaky(z):
    return np.where(z > 0, 1.0, ALPHA)


class BarrierNet:
    def __init__(self, dims=(66, 128, 128, 128, 1), c=10.0, seed=0):
        rng = np.random.default_rng(seed)
        self.dims = dims
        self.c = c
        self.W = [rng.normal(0, np.sqrt(2.0 / dims[i]), (dims[i + 1], dims[i])) for i in range(len(dims) - 1)]
        self.b = [np.zeros(dims[i + 1]) for i in range(len(dims) - 1)]
        self.mu = np.zeros(dims[0])
        self.u = [rng.normal(size=w.shape[0]) for w in self.W]
        for i, w in enumerate(self.W):
            self.W[i] = w / max(1.0, self._sigma(i, 20))

    # ---- spectral norm ----------------------------------------------------------
    def _sigma(self, i, iters=1):
        w, u = self.W[i], self.u[i]
        for _ in range(iters):
            v = w.T @ u; v /= np.linalg.norm(v) + 1e-12
            u = w @ v; u /= np.linalg.norm(u) + 1e-12
        self.u[i] = u
        self._v = v
        return float(u @ (w @ v))

    # ---- forward / backward -----------------------------------------------------
    def _eff(self):
        sig = [self._sigma(i, 1) for i in range(len(self.W))]
        scale = [1.0 / max(1.0, s) for s in sig]
        return sig, scale

    def forward(self, x, train=False):
        a = x - self.mu
        cache = [a]
        sig, scale = self._eff() if train else (None, [1.0] * len(self.W))
        zs = []
        for i, (w, b) in enumerate(zip(self.W, self.b)):
            z = (a @ w.T) * scale[i] + b
            zs.append(z)
            a = leaky(z) if i < len(self.W) - 1 else z
            cache.append(a)
        h = self.c * a[:, 0]
        return h, (cache, zs, sig, scale)

    def predict(self, x, batch=20000):
        """Evaluate with the projected weights (exact spectral norm <= 1), as deployed."""
        saved = [w.copy() for w in self.W]
        for i, w in enumerate(self.W):
            sg = np.linalg.svd(w, compute_uv=False)[0]
            if sg > 1.0:
                self.W[i] = w / sg
        out = np.empty(len(x))
        for s in range(0, len(x), batch):
            out[s:s + batch] = self.forward(x[s:s + batch])[0]
        self.W = saved
        return out

    def grad_x(self, x):
        """dh/dx for each row (exact: the network is piecewise linear)."""
        a = x - self.mu
        zs = []
        for i, (w, b) in enumerate(zip(self.W, self.b)):
            z = a @ w.T + b
            zs.append(z)
            a = leaky(z) if i < len(self.W) - 1 else z
        g = np.ones((len(x), 1)) * self.c
        for i in reversed(range(len(self.W))):
            if i < len(self.W) - 1:
                g = g * dleaky(zs[i])
            g = g @ self.W[i]
        return g

    def step(self, x, y, wcls, margin, lam, opt):
        h, (cache, zs, sig, scale) = self.forward(x, train=True)
        viol = np.maximum(0.0, margin - y * h)
        loss = np.mean(wcls * viol)
        dh = -(wcls * y * (viol > 0)) / len(x)                       # d loss / d h
        g = (self.c * dh)[:, None]                                   # grad at last pre-activation
        gW, gb = [None] * len(self.W), [None] * len(self.W)
        for i in reversed(range(len(self.W))):
            if i < len(self.W) - 1:
                g = g * dleaky(zs[i])
            gW[i] = (g.T @ cache[i]) * scale[i]
            gb[i] = g.sum(axis=0)
            g = (g @ self.W[i]) * scale[i]
        pen = 0.0
        for i in range(len(self.W)):                                 # spectral-norm penalty
            s = sig[i]
            if s > 1.0:
                pen += lam * (s - 1.0) ** 2
                u = self.u[i]; v = self.W[i].T @ u; v /= np.linalg.norm(v) + 1e-12
                gW[i] += 2 * lam * (s - 1.0) * np.outer(u, v)
        opt.update(self, gW, gb)
        return loss + pen

    def project(self):
        """Exact projection to spectral norm <= 1 (end of training)."""
        for i, w in enumerate(self.W):
            s = np.linalg.svd(w, compute_uv=False)[0]
            if s > 1.0:
                self.W[i] = w / s

    def state(self):
        d = {"c": np.array(self.c), "mu": self.mu}
        for i, (w, b) in enumerate(zip(self.W, self.b)):
            d[f"W{i + 1}"] = w
            d[f"b{i + 1}"] = b
        return d

    @classmethod
    def from_state(cls, d):
        dims = [d["W1"].shape[1]] + [d[f"W{i}"].shape[0] for i in range(1, 5)]
        net = cls(tuple(dims), float(d["c"]), 0)
        net.W = [np.array(d[f"W{i}"], float) for i in range(1, 5)]
        net.b = [np.array(d[f"b{i}"], float) for i in range(1, 5)]
        net.mu = np.array(d["mu"], float)
        return net


class Adam:
    def __init__(self, net, lr=1e-3, b1=0.9, b2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps, self.t = lr, b1, b2, eps, 0
        self.mW = [np.zeros_like(w) for w in net.W]; self.vW = [np.zeros_like(w) for w in net.W]
        self.mb = [np.zeros_like(b) for b in net.b]; self.vb = [np.zeros_like(b) for b in net.b]

    def update(self, net, gW, gb):
        self.t += 1
        c1 = 1 - self.b1 ** self.t; c2 = 1 - self.b2 ** self.t
        for i in range(len(net.W)):
            for p, g, m, v in ((net.W, gW, self.mW, self.vW), (net.b, gb, self.mb, self.vb)):
                m[i] = self.b1 * m[i] + (1 - self.b1) * g[i]
                v[i] = self.b2 * v[i] + (1 - self.b2) * g[i] ** 2
                p[i] = p[i] - self.lr * (m[i] / c1) / (np.sqrt(v[i] / c2) + self.eps)


def train(net, X, y, Xv, yv, seed, epochs=500, batch=256, lr=1e-3, margin=0.1, lam=1.0,
          w_unsafe=4.0, patience=25, verbose=True):
    rng = np.random.default_rng(seed)
    opt = Adam(net, lr)
    net.mu = X.mean(axis=0)
    wcls = np.where(y < 0, w_unsafe, 1.0)
    best, best_state, bad = np.inf, None, 0
    for ep in range(epochs):
        order = rng.permutation(len(X))
        tot = 0.0
        for s in range(0, len(X), batch):
            idx = order[s:s + batch]
            tot += net.step(X[idx], y[idx], wcls[idx], margin, lam, opt) * len(idx)
        hv = net.predict(Xv)
        vloss = np.mean(np.where(yv < 0, w_unsafe, 1.0) * np.maximum(0, margin - yv * hv))
        if vloss < best - 1e-5:
            best, bad = vloss, 0
            best_state = ([w.copy() for w in net.W], [b.copy() for b in net.b])
        else:
            bad += 1
        if verbose and (ep % 10 == 0 or bad == 0):
            acc = np.mean(np.sign(hv) == yv)
            print(f"  epoch {ep:3d}  train {tot / len(X):.4f}  val {vloss:.4f}  val-acc {acc:.4f}", flush=True)
        if bad >= patience:
            break
    net.W, net.b = best_state
    net.project()
    return net


def lipschitz_lower_bound(net, X, seed, n_start=4000, iters=300, step=0.02):
    """Empirical lower bound on Lip(h): adversarial ascent on |h(x) - h(y)| / ||x - y||.

    Starts from data points and from Gaussian perturbations of them, ascends the ratio
    for random pairs (x, y = x + delta), and returns the largest ratio found. A search
    result, therefore a lower bound; it certifies nothing.
    """
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X), n_start, replace=True)
    x = X[idx] + rng.normal(0, 0.05, (n_start, X.shape[1]))
    d = rng.normal(size=x.shape); d *= 0.05 / np.linalg.norm(d, axis=1, keepdims=True)
    best = 0.0
    for it in range(iters):
        y = x + d
        hx, hy = net.predict(x), net.predict(y)
        r = np.linalg.norm(d, axis=1)
        ratio = np.abs(hx - hy) / r
        best = max(best, float(ratio.max()))
        sgn = np.sign(hx - hy)[:, None]
        gx, gy = net.grad_x(x), net.grad_x(y)
        # ascent on the ratio w.r.t. x and the offset d
        gd = (-sgn * gy) / r[:, None] - (np.abs(hx - hy) / r ** 3)[:, None] * d
        gx_ = sgn * (gx - gy) / r[:, None]
        x = x + step * gx_ / (np.linalg.norm(gx_, axis=1, keepdims=True) + 1e-9) * 0.3
        d = d + step * 0.05 * gd / (np.linalg.norm(gd, axis=1, keepdims=True) + 1e-9)
        d *= np.clip(0.05 / np.linalg.norm(d, axis=1, keepdims=True), 0.2, 5.0)
    # the gradient norm at the best points is also a valid lower bound
    gn = np.linalg.norm(net.grad_x(x), axis=1).max()
    return max(best, float(gn))
