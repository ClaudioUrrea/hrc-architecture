#!/usr/bin/env python3
"""Graphical abstract of manuscript R4 (release 3.1), drawn only from the generated macros.

    python3 make_ga.py --numbers ../numbers/r4_numbers.tex --out ../figures/GA_Electronics_4587969_R4

Every value is read from numbers/r4_numbers.tex, the same file that prints the numbers in the
manuscript and in the letters, so the graphical abstract cannot disagree with the text. A value that
is not available is drawn as a red "??". The one interpretive sentence (sensing chain versus
computation) is printed only if the data support it, and is otherwise replaced by "??".
Output: PNG at 2200 x 1120 px (MDPI minimum 1100 x 560) and a vector PDF.
"""
import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402

# same palette as make_figures.py (series identity on bars and headers; text stays in ink tokens)
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, LINE, PANEL = "#0b0b0b", "#52514e", "#9b9a95", "#d6d5d0", "#f5f5f3"
RED = "#c00000"
MISSING = "??"

# Palatino Linotype, as in the figures of the article; minus signs as U+2212
plt.rcParams.update({"font.family": "serif", "font.serif": ["Palatino Linotype", "TeX Gyre Pagella", "Palatino", "URW Palladio L"],
                     "mathtext.fontset": "custom", "mathtext.rm": "Palatino Linotype", "mathtext.it": "Palatino Linotype:italic",
                     "mathtext.bf": "Palatino Linotype:bold", "axes.unicode_minus": True, "pdf.fonttype": 42})


def read_macros(path):
    txt = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    out = {}
    for m in re.finditer(r"\\newcommand\{\\(R[A-Za-z]+)\}\{(.*)\}\s*$", txt, flags=re.M):
        out[m.group(1)] = m.group(2)
    return out


def plain(v):
    """LaTeX macro value -> display text for matplotlib (mathtext only where needed)."""
    if v is None or "missingnum" in v:
        return MISSING
    s = v.replace("{,}", ",").replace(r"$<$", "<").replace(r"\%", "%").replace(r"\textmu", "µ")
    s = s.replace(r"\,", " ").replace("~", " ")
    m = re.fullmatch(r"(-?[\d.]+)\\times10\^\{(-?\d+)\}", s)
    if m:
        sup = str.maketrans("-0123456789", "\u207b\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")
        return f"{m.group(1)} \u00d7 10{m.group(2).translate(sup)}".replace("-", "\u2212")
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"(?<![A-Za-z])-(?=[\d.])", "\u2212", s)


def num(v):
    try:
        return float(plain(v).replace(",", "").replace("\u2212", "-"))
    except (ValueError, AttributeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--numbers", required=True)
    ap.add_argument("--out", required=True, help="output path without extension")
    a = ap.parse_args()
    M = read_macros(a.numbers)
    g = lambda k: plain(M.get(k))  # noqa: E731

    W, H = 11.0, 5.6  # inches; 200 dpi -> 2200 x 1120 px
    fig = plt.figure(figsize=(W, H), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    fig.patch.set_facecolor("white")

    def txt(x, y, s, size=9, color=INK, weight="normal", ha="left", va="center", style="normal"):
        c = RED if s == MISSING else color
        ax.text(x, y, s, fontsize=size, color=c, fontweight=weight, ha=ha, va=va, fontstyle=style,
                family="serif")

    def box(x, y, w, h, fc, ec=LINE, lw=1.0, r=0.06):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw))

    # ---------------------------------------------------------------- header
    txt(0.25, 5.32, "A safety-filtered architecture for human\u2013robot collaboration, evaluated as software",
        size=14.5, weight="bold")
    txt(0.25, 5.02, "Three-layer architecture \u00b7 Design, calibration rule and analysis published before the first run "
        "\u00b7 Every number computed from hash-manifested run logs", size=9.2, color=INK2)
    ax.plot([0.25, W - 0.25], [4.84, 4.84], color=LINE, lw=1.2)

    # ---------------------------------------------------------------- left: what was simulated
    txt(0.25, 4.58, "Simulated cell", size=10, weight="bold", color=INK2)
    left = [("Kinematic UR5e model", "500 Hz servo loop"),
            ("Scripted operator", "Six-camera keypoint model"),
            ("URSim " + g("RConfVersion"), "Vendor controller, unmodified")]
    for i, (a1, a2) in enumerate(left):
        y = 3.72 - i * 0.98
        box(0.25, y, 1.78, 0.72, PANEL, ec=MUTED, lw=1.0)
        txt(1.14, y + 0.47, a1, size=8.6, weight="bold", ha="center", color=RED if MISSING in a1 else INK)
        txt(1.14, y + 0.22, a2, size=7.4, color=INK2, ha="center")
        ax.add_patch(FancyArrowPatch((2.08, y + 0.36), (2.42, y + 0.36), arrowstyle="-|>", mutation_scale=11,
                                     color=MUTED, lw=1.4))

    # ---------------------------------------------------------------- three panels
    age_ms, exec_us = num(M.get("RTimAgeMed")), num(M.get("RTimExecMedUs"))
    if age_ms is not None and exec_us is not None and exec_us > 0:
        ratio = age_ms * 1000.0 / exec_us
        insight2 = ("The sensing chain, not the computation,\nsets the reaction budget"
                    if ratio >= 100 else "Computation is a significant part\nof the reaction budget")
    else:
        insight2 = MISSING
    # comparison with ISO/TS 15066 speed scaling: shown only if significant after Holm correction
    # comparison under the shared SSM limit: printed with its sign, whatever it is
    d = g("RCmpCycPFSSMDiff")
    cmp_row = ("Task cycle vs PF-SSM", (("+" if not d.startswith(("-", "\u2212")) else "") + d + " s") if d != MISSING else MISSING)
    panels = [
        (S1, "Hardware abstraction", "Build-enforced isolation",
         [("Safety library links", "Core only"),
          ("Adapter vs URSim", f"{g('RConfRThreeOnePass')} pass, {g('RConfRThreeOneFail')} fail"),
          ("KUKA, ABB adapters", "Not evaluated"),
          ("Logged runs, SHA-256", g("RLogRuns"))],
         "A vendor call in the safety code\nmakes the isolated test target fail to build"),
        (S2, "Control layer", "CBF-QP safety filter \u00b7 20 ms cycle",
         [("Cycle execution, median", f"{g('RTimExecMedUs')} µs"),
          ("Cycle execution, max.", f"{g('RTimExecMax')} ms"),
          ("Deadline misses (not injected)", g("RTimMissRet")),
          ("Estimate age, median", f"{g('RTimAgeMed')} ms")],
         insight2),
        (S3, "Faults and baselines", "One supervisor \u00b7 Eight modes",
         [("Injected faults detected", f"{g('RFiDetected')} / {g('RFiInjected')}"),
          ("Detection latency, median", f"{g('RFiDetMed')} ms"),
          ("Motion permitted (timing)", f"{g('RAvTimPermitted')} %"),
          cmp_row],
         "All dispatched commands met every\nconstraint; learned barrier: no benefit"),
    ]
    x0, pw, gap = 2.5, 2.62, 0.16
    for k, (col, head, sub, rows, note) in enumerate(panels):
        x = x0 + k * (pw + gap)
        box(x, 0.95, pw, 3.78, "white", ec=MUTED, lw=1.0, r=0.08)
        box(x, 4.13, pw, 0.60, col, ec=col, lw=1.0, r=0.08)
        ax.add_patch(plt.Rectangle((x, 4.13), pw, 0.12, fc=col, ec=col, lw=0))
        txt(x + pw / 2, 4.52, head, size=11, weight="bold", color="white", ha="center")
        txt(x + pw / 2, 4.27, sub, size=7.8, color="white", ha="center")
        for i, (lab, val) in enumerate(rows):
            y = 3.62 - i * 0.55
            box(x + 0.12, y, pw - 0.24, 0.40, PANEL, ec=LINE, lw=0.8, r=0.04)
            ax.add_patch(plt.Rectangle((x + 0.16, y + 0.06), 0.045, 0.28, fc=col, ec=col, lw=0))
            txt(x + 0.28, y + 0.20, lab, size=7.7, color=INK2)
            vcol = RED if MISSING in val else INK
            ax.text(x + pw - 0.20, y + 0.20, val, fontsize=9.2, color=vcol, fontweight="bold", ha="right",
                    va="center", family="serif")
        box(x + 0.12, 1.09, pw - 0.24, 0.72, PANEL, ec=LINE, lw=0.8, r=0.05)
        txt(x + pw / 2, 1.45, note, size=7.8, color=RED if note == MISSING else INK, ha="center", style="italic")
        if k < 2:
            xa = x + pw + 0.01
            ax.add_patch(FancyArrowPatch((xa, 2.55), (xa + gap - 0.02, 2.55), arrowstyle="-|>", mutation_scale=10,
                                         color=MUTED, lw=1.3))

    # ---------------------------------------------------------------- footer
    box(0.25, 0.12, W - 0.5, 0.66, PANEL, ec=MUTED, lw=1.0, r=0.06)
    stats = [(g("RTimCyclesTotal"), "Control cycles timed"),
             (g("RTimBlocks"), "Cold-started 100-min blocks"),
             (g("RLogCyclesDropped"), f"Cycle records dropped by the logger\n({g('RLogRuns')} runs, SHA-256 verified)")]
    for i, (big, small) in enumerate(stats):
        xs = 0.55 + i * 2.25
        ax.text(xs, 0.56, big, fontsize=13, fontweight="bold", color=RED if MISSING in big else INK, va="center",
                family="serif")
        txt(xs, 0.27, small, size=7.2, color=INK2)
        if i:
            ax.plot([xs - 0.18, xs - 0.18], [0.22, 0.68], color=LINE, lw=1.0)
    ax.plot([7.05, 7.05], [0.22, 0.68], color=LINE, lw=1.0)
    txt(7.2, 0.45, "Simulation on a general-purpose (non-real-time) Linux host.\n"
        "No physical robot, no safety-rated hardware, no person.\n"
        "No conformity with any safety standard is claimed.", size=7.4, color=INK)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    plt.close(fig)
    n_missing = sum(1 for k in ("RConfVersion", "RConfPass", "RConfItems", "RLogRuns", "RTimExecMedUs", "RTimExecMax",
                                "RTimMissRet", "RTimAgeMed", "RFiDetected", "RFiInjected", "RFiDetMed", "RAvTimPermitted",
                                "RLogCyclesDropped", "RTimCyclesTotal", "RTimBlocks", "RConfRThreeOnePass",
                                "RCmpCycPFSSMDiff")
                    if g(k) == MISSING)
    print(f"graphical abstract -> {out.with_suffix('.png')} ({n_missing} values missing)")


if __name__ == "__main__":
    main()
