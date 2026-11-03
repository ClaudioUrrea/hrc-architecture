#!/usr/bin/env python3
"""Data figures of manuscript R3, drawn only from results.json and results_extra.json.

    python3 make_figures.py --results results.json --extra results_extra.json --out ../figures

A figure whose inputs are missing is written as a page that says so (never as an empty or
example plot), so a missing result is visible in the compiled PDF.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# reference categorical palette (light mode), fixed order; text in ink tokens, never series colour
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
INK, INK2, GRID, MUTED = "#0b0b0b", "#52514e", "#e4e3df", "#9b9a95"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "legend.frameon": False, "pdf.fonttype": 42, "savefig.bbox": "tight", "savefig.dpi": 300})
CAT_LABEL = {"tracking_loss": "Tracking loss", "sensor_timeout": "Sensor timeout", "computational_overrun": "Comp. overrun",
             "hardware_communication": "HW communication", "configuration_inconsistency": "Config. inconsistency",
             "network_partition": "Network partition", "constraint_violation": "Lunge (constraint)", "memory_allocation": "Memory allocation"}
CAT_ORDER = list(CAT_LABEL)


def missing(path, what):
    fig, ax = plt.subplots(figsize=(6.5, 2.0))
    ax.axis("off")
    ax.text(0.5, 0.5, f"MISSING INPUT: {what}\n(figure generated only from results files)", ha="center", va="center",
            color="#c00000", fontsize=11)
    fig.savefig(path)
    plt.close(fig)


def label(ax, s):
    ax.set_title(s, loc="left", fontsize=8.5, fontweight="bold", color=INK)


# ------------------------------------------------------------------------------- timing
def fig_timing(res, ex, out):
    t, tb = res.get("timing"), (ex or {}).get("timing_behaviour")
    if not t or not tb:
        return missing(out, "timing (results.json: timing; results_extra.json: timing_behaviour)")
    fig, axs = plt.subplots(2, 2, figsize=(7.0, 4.6))
    # (a) pooled execution time, CCDF on log scale
    b = np.asarray(tb["hist"]["exec_bins_ms"]); h = np.asarray(tb["hist"]["exec"], float)
    ccdf = 1 - np.cumsum(h) / h.sum()
    ax = axs[0, 0]
    keep = ccdf > 0
    ax.step(b[1:][keep], ccdf[keep], where="post", color=S1, lw=1.5)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.axvline(20, color=INK2, lw=1, ls="--"); ax.text(20, 0.3, " 20 ms\n Deadline", color=INK2, fontsize=7, va="top")
    ax.set_xlabel("Cycle execution time (ms), injected overruns excluded"); ax.set_ylabel("Fraction of cycles exceeding")
    label(ax, "(a) Pooled execution time, all blocks")
    # (b) per-block maximum
    ax = axs[0, 1]
    mx = np.sort([x["exec_max_ms"] for x in tb["blocks"]])
    ax.plot(np.arange(1, len(mx) + 1), mx, "o", ms=3, color=S1)
    ax.axhline(20, color=INK2, lw=1, ls="--")
    ax.set_yscale("log"); ax.set_xlabel("Block (sorted by its maximum)"); ax.set_ylabel("Maximum execution time (ms)")
    label(ax, "(b) Maximum of each 100-min block")
    # (c) stage medians
    ax = axs[1, 0]
    st = t["stage_median_ms"]
    keys = ["state", "nominal", "geo", "learned", "qp", "dispatch", "log"]
    names = ["State read", "Nominal controller", "Geometric rows", "Learned barrier", "QP + SSM", "Dispatch", "Record"]
    v = [st[k] * 1000 for k in keys]
    ax.barh(names[::-1], v[::-1], color=S1, height=0.6)
    for i, x in enumerate(v[::-1]):
        ax.text(x, i, f" {x:.3g}", va="center", fontsize=7, color=INK)
    ax.set_xlabel("Median per cycle (µs)"); ax.grid(axis="y", visible=False)
    label(ax, "(c) Stage medians")
    # (d) estimate age
    ax = axs[1, 1]
    b = np.asarray(tb["hist"]["age_bins_ms"]); h = np.asarray(tb["hist"]["age"], float)
    ax.bar(b[:-1], h / h.sum(), width=np.diff(b), align="edge", color=S2, lw=0)
    ax.set_xlim(b[np.nonzero(h)[0][0]] - 5, b[np.nonzero(h)[0][-1]] + 5)
    ax.set_xlabel("Age of the human-state estimate at use (ms)"); ax.set_ylabel("Fraction of cycles")
    label(ax, "(d) Sensing-data age")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


# ------------------------------------------------------------------------------- ablation
def fig_ablation(res, ex, out):
    rows = (ex or {}).get("ablation_runs")
    if not rows:
        return missing(out, "ablation (results_extra.json: ablation_runs)")
    order = ["A0", "A1", "A2a", "A2b", "A2c", "A2", "A3"]
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.6))
    for ax, key, ylab, title in ((axs[0], "median_ms", "Run median (ms)", "(a) Median execution time per run"),
                                 (axs[1], "max_ms", "Run maximum (ms)", "(b) Maximum execution time per run")):
        for j, (load, col) in enumerate((("idle", S1), ("load", S2))):
            for i, c in enumerate(order):
                y = [r[key] for r in rows if r["configuration"] == c and r["load"] == load]
                x = i + (j - 0.5) * 0.28 + np.linspace(-0.08, 0.08, len(y)) if y else []
                ax.plot(x, y, "o", ms=3, color=col, alpha=0.85, label={"idle": "Idle host", "load": "Loaded host"}.get(load, f"{load.capitalize()} host") if i == 0 else None)
        ax.set_xticks(range(len(order))); ax.set_xticklabels(order)
        ax.set_yscale("log"); ax.set_ylabel(ylab); label(ax, title)
        if key == "max_ms":
            ax.axhline(20, color=INK2, lw=1, ls="--")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2, fontsize=7, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig(out); plt.close(fig)


# ------------------------------------------------------------------------------- faults
def fig_faults(res, ex, out):
    fi = res.get("fault_injection")
    if not fi or not fi.get("rows"):
        return missing(out, "fault injection (results.json: fault_injection.rows)")
    rows = fi["rows"]
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.8))
    ax = axs[0]
    cats = [c for c in CAT_ORDER if any(r["category"] == c and r["detection_ms"] is not None for r in rows)]
    for i, c in enumerate(cats):
        y = [r["detection_ms"] for r in rows if r["category"] == c and r["detection_ms"] is not None]
        ax.plot(np.full(len(y), i) + np.random.default_rng(i).uniform(-0.18, 0.18, len(y)), y, "o", ms=2.5, color=S1, alpha=0.6)
        ax.plot([i - 0.3, i + 0.3], [np.median(y)] * 2, color=INK, lw=1.5)
    ax.set_xticks(range(len(cats))); ax.set_xticklabels([CAT_LABEL[c] for c in cats], rotation=35, ha="right")
    ax.set_yscale("log"); ax.set_ylabel("Injection to detection (ms)"); label(ax, "(a) Detection latency (bar = median)")
    ax = axs[1]
    pc = fi["per_category"]
    cats2 = [c for c in CAT_ORDER if c in pc]
    det = [pc[c]["detected"] for c in cats2]
    ws = [pc[c]["undetected_while_stopped"] for c in cats2]
    oth = [pc[c]["undetected_other"] for c in cats2]
    y = np.arange(len(cats2))
    ax.barh(y, det, color=S1, height=0.6, label="Detected")
    ax.barh(y, ws, left=det, color=MUTED, height=0.6, label="Not detected: cell already stopped")
    ax.barh(y, oth, left=np.add(det, ws), color=S2, height=0.6, label="Not detected: other")
    ax.set_yticks(y); ax.set_yticklabels([CAT_LABEL[c] for c in cats2]); ax.invert_yaxis()
    ax.set_xlabel("Injections"); ax.grid(axis="y", visible=False)
    ax.legend(fontsize=6.5, loc="upper center", bbox_to_anchor=(0.45, -0.22), ncol=2)
    label(ax, "(b) Outcome of each injection")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


# ------------------------------------------------------------------------------- comparison
def fig_compare(res, ex, out):
    bc = res.get("baseline_comparison")
    if not bc or not bc.get("rows"):
        return missing(out, "baseline comparison (results.json: baseline_comparison.rows)")
    rr = bc["rows"]
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.2))
    for ax, ep, sc, unit, title in ((axs[0], "task_cycle_s", 1, "s", "(a) Task cycle, proposed $-$ baseline"),
                                    (axs[1], "min_sep_m", 1000, "mm", "(b) Minimum separation, proposed $-$ baseline")):
        rs = [r for r in rr if r["endpoint"] == ep]
        for i, r in enumerate(rs):
            lo, hi = r["ci95"]
            col = S1 if r["p_holm"] < 0.05 else MUTED
            ax.plot([lo * sc, hi * sc], [i, i], color=col, lw=2, solid_capstyle="round")
            ax.plot(r["mean_diff"] * sc, i, "o", ms=6, color=col, mec="white", mew=1)
        ax.axvline(0, color=INK2, lw=1)
        ax.set_yticks(range(len(rs))); ax.set_yticklabels([{"hc_cbf": "HC-CBF", "ssm": "SSM", "pf": "PF"}[r["baseline"]] for r in rs])
        ax.set_xlabel(f"Paired mean difference ({unit}), BCa 95% CI"); ax.grid(axis="y", visible=False)
        label(ax, title)
    fig.text(0.01, -0.04, "Blue: Holm-adjusted p < 0.05; grey: not significant after correction.", color=INK2, fontsize=7)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


# ------------------------------------------------------------------------------- safety behaviour
def fig_behaviour(res, ex, out):
    tb, cb, ib = [(ex or {}).get(k) for k in ("timing_behaviour", "compare_behaviour", "injection_behaviour")]
    if not tb:
        return missing(out, "safety-layer behaviour (results_extra.json: timing_behaviour)")
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.6))
    ax = axs[0]
    b = np.asarray(tb["hist"]["sep_bins_m"]); h = np.asarray(tb["hist"]["sep"], float)
    ccdf_low = np.cumsum(h) / h.sum()
    ax.step(b[1:], np.maximum(ccdf_low, 1e-9), where="post", color=S1, lw=1.5, label="Timing campaign")
    if cb:
        h2 = np.asarray(cb["hist"]["sep"], float)
        ax.step(b[1:], np.maximum(np.cumsum(h2) / h2.sum(), 1e-9), where="post", color=S2, lw=1.5, label="Comparison campaign")
    ax.axvline(0.15, color=INK2, lw=1, ls="--"); ax.text(0.15, 0.5, " 0.15 m floor", color=INK2, fontsize=7)
    ax.set_yscale("log"); ax.set_xlim(0, 1.5); ax.set_ylim(1e-8, 1.5)
    ax.set_xlabel("Minimum robot–human separation (m)"); ax.set_ylabel("Fraction of cycles below")
    ax.legend(fontsize=7, loc="lower right"); label(ax, "(a) Separation distribution")
    ax = axs[1]
    modes = ["nominal", "low_confidence", "degraded_stream", "geometric_fallback", "overrun_shed", "protective_stop",
             "protective_stop_latched", "emergency_stop"]
    names = ["Nominal", "Low confidence", "Degraded stream", "Geometric fallback", "Overrun shed", "Protective stop", "Prot. stop (latched)", "Emergency stop"]
    camps = [(tb, "Timing", S1), (cb, "Comparison", S2), (ib, "Injection", S3)]
    camps = [c for c in camps if c[0]]
    y = np.arange(len(modes))
    w = 0.8 / len(camps)
    for j, (bh, nm, col) in enumerate(camps):
        v = np.array([bh["mode_fraction"][m] * 100 for m in modes])
        nz = v > 0
        ax.barh((y + (j - (len(camps) - 1) / 2) * w)[nz], v[nz], height=w * 0.9, color=col, label=nm)
    ax.set_xscale("log"); ax.set_xlim(1e-4, 150); ax.set_yticks(y); ax.set_yticklabels(names); ax.invert_yaxis()
    ax.set_xlabel("Share of cycles (%)"); ax.grid(axis="y", visible=False); ax.legend(fontsize=7, loc="center right")
    label(ax, "(b) Supervisor mode occupancy")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--extra", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    res = json.loads(Path(a.results).read_text()) if Path(a.results).exists() else {}
    ex = json.loads(Path(a.extra).read_text()) if a.extra and Path(a.extra).exists() else {}
    fig_timing(res, ex, out / "Fig_timing.pdf")
    fig_ablation(res, ex, out / "Fig_ablation.pdf")
    fig_faults(res, ex, out / "Fig_faults.pdf")
    fig_compare(res, ex, out / "Fig_compare.pdf")
    fig_behaviour(res, ex, out / "Fig_behaviour.pdf")
    print("figures ->", out)


if __name__ == "__main__":
    main()
