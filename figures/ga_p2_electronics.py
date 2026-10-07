#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Graphical abstract for P2 - "Vendor-Neutral Embedded Control Architecture for
Safety-Critical Human-Robot Collaboration: Hardware Abstraction, Bounded-Latency
Execution and Industrial Protocol Integration Evaluated Against Simulated Vendor
Interfaces".

Target: MDPI Electronics, Manuscript ID electronics-4587969 (major revision, round 1).
Author: Claudio Urrea, University of Santiago of Chile.

MDPI graphical abstract (GA) compliance notes
---------------------------------------------
  * Scope, stated on the artwork itself.  Every quantity was produced against
    SIMULATED robot, sensor and PLC interfaces; no physical device and no human
    participant was involved, and no safety-standard conformity is claimed.
  * Original composition.  Figure 1 of the manuscript is a vertical stack of
    three layers; this is a left-to-right data path from three robot platforms
    to the plant, with the measured latencies as the organizing element.  No
    subfigure of the paper is reused.
  * Output PNG at 2200 x 1120 px, twice the 1100 x 560 px minimum
    (width x height).
  * Sans-serif typeface (Liberation Sans, metric-compatible with Arial, on the
    MDPI recommended list).  Nothing below 9 pt at the export size.
  * Decimal points, never decimal commas.
  * Vendor names appear as plain text only, exactly as in the manuscript: no
    logos, no trademarked artwork, no copyrighted material, and no heading
    reading "Graphical Abstract".

Layout conventions (revision of 18 August 2026)
-----------------------------------------------
  * CLEARANCE.  Nothing touches or crosses a card outline.  Every card reserves
    an inner margin of PAD units on all four sides (see `inner()`), rows are
    positioned from that rectangle rather than by absolute offsets, and the
    header band is drawn so that its rounded lower corners are filled instead of
    being left as white notches on the outline.
  * CAPITALIZATION.  Card titles are in title case and every other phrase opens
    with a capital, matching the figures of the manuscript.  Protocol and unit
    names keep their canonical case (OPC-UA, EtherCAT, ms, h).

Revision R1 (September 2026) - changes forced by the review
-----------------------------------------------------------
  * The extrapolated MTBF of 847 h is WITHDRAWN and no longer appears in the
    footer strip.  It is not derivable from a 200 h observation of a population
    whose observed MTBF is of the order of one hour.  The footer now carries the
    operator-intervention MTBF with its exact Poisson interval, which is the
    longest figure the data will bear.
  * "Deterministic execution" is replaced by "bounded-latency execution".  What
    is claimed is a measured latency distribution with a stated maximum over a
    stated number of cycles, not a proven worst-case bound.
  * The architectural ablation is added: the layering costs about 0.3 ms of
    median cycle time against a monolithic implementation and buys the bounded
    tail, isolated testability and vendor portability.  Saying so on the GA is
    deliberate - it is the one result that attributes the rest to the
    architecture rather than to the control algorithm.
  * PLC commissioning is stated as the measured range 3.5-3.8 h rather than
    "under 4 hours", and the 40-45 h alternative is marked as the author's own estimate
    (no documentary record exists), not a measurement.
  * The ABB interface is named as Robot Web Services / Externally Guided Motion,
    matching the vendor documentation cited in the manuscript.
  * Every layer strip carries a measured / simulated tag, matching Table 3.

Revision of October 2026 - further changes forced by the review
---------------------------------------------------------------
  * The architectural claim is split in two, because the widened ablation
    (seven configurations, 30 condition cells each) supports only half of what
    the previous version asserted.  The layering costs 0.3 ms of median cycle
    time and does NOT improve the latency tail: the monolithic baseline holds
    the lowest maximum of the seven.  The control-layer note therefore states
    the cost and the conditional tail result, not an architectural tail
    advantage.
  * The footer no longer mixes two data sets.  Availability and mean recovery
    are now taken from the 200 h continuous run alone, at the per-mode recovery
    means observed inside it; the 450-injection campaign is a cross-check and is
    no longer the source of the recovery figure.  The mean auto-recovery time
    printed is 4.0 s (10.0 min over 150 automatically recovered faults), not the
    3.5 s injection-campaign mean.
  * The deadline-miss cell reports the grain at which independence is
    defensible - no miss in 120 cold-started 100-minute blocks - rather than a
    per-cycle count that invited a rule-of-three bound the paper has withdrawn.

  * Revision of 7 October 2026 (consistency pass): the protocol rows now print the
    medians of Section 6.2 and Figure 6c (OPC-UA read 4.2 ms, Modbus TCP function
    code 03 7.1 ms) instead of rounded upper bounds ("< 5 ms", "< 10 ms") that the
    paper's own medians for subscriptions (5.8 ms) did not support; the block
    length is stated as 100 minutes.

Every quantity printed here comes from the abstract and Sections 3-9 of the
revised manuscript and is collected in NUMBERS below.

Run:  python3 ga_p2_electronics.py
Out:  ./figures_ga/GA_Electronics_4587969.png  (2200 x 1120 px, RGB, 600 dpi)
"""

from pathlib import Path

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image

# ==============================================================================
# OUTPUT LOCATION
# ==============================================================================
OUT_DIR = Path(__file__).resolve().parent / 'figures_ga'
OUT_DIR.mkdir(exist_ok=True)

# ==============================================================================
# NUMBERS - single source of truth, mirrors the abstract
# ==============================================================================
NUMBERS = dict(
    api_median=2.1, api_p95=4.8, loop_hz=50, jitter_pct=1, fusion_ms=4.5,
    cbf_ms=1.8, cbf_grad_ms=2.2, critical_path_ms=6.2, opcua_ms=4.2, modbus_ms=7.1,
    ethercat_ms=1, reuse_pct=86, loc_lo=456, loc_hi=523,
    plc_lo=3.5, plc_hi=3.8, plc_custom_lo=40, plc_custom_hi=45,
    avail_pct=98.5, stress_h=200, recovery_s=4.0, blocks=120,
    mtbf_h=33.3, mtbf_lo=15.3, mtbf_hi=90.8, arch_cost_ms=0.3,
    cycles=3.6e7,
)

# ==============================================================================
# STYLE
# ==============================================================================
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Liberation Sans', 'Arial', 'Helvetica', 'DejaVu Sans'],
    'axes.linewidth': 0.0,
})

C = {
    'physical':    '#0072B2',   # blue       - hardware abstraction layer
    'control':     '#D55E00',   # vermillion - real-time control layer
    'integration': '#009E73',   # green      - integration layer
    'ink':         '#1A1A1A',
    'grey':        '#6E6E6E',
    'rule':        '#C6C6C6',
    'wash':        '#F4F6F8',
    'panel':       '#FFFFFF',
    'metal':       '#DCE3E8',
}

W, H = 1100.0, 560.0
DPI = 200
FIGSIZE = (W / 100.0, H / 100.0)      # -> 2200 x 1120 px

PAD = 14.0                            # inner margin reserved by every card
HEADER_H = 54.0                       # title band: one title plus one subtitle
ROW_H, ROW_GAP = 30.0, 10.0           # measurement rows inside a layer

fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.set_axis_off()
ax.add_patch(Rectangle((0, 0), W, H, facecolor='white', zorder=0))


# ==============================================================================
# HELPERS
# ==============================================================================
def layer(x0, y0, w, h, title, subtitle, accent):
    """Layer card with a two-line coloured header.

    The plain rectangle under the rounded header fills the lower rounded
    corners; without it the card outline shows two white notches.
    """
    ax.add_patch(FancyBboxPatch((x0, y0), w, h,
                                boxstyle='round,pad=0,rounding_size=10',
                                facecolor=C['panel'], edgecolor=C['rule'],
                                linewidth=1.1, zorder=2))
    ax.add_patch(FancyBboxPatch((x0, y0 + h - HEADER_H), w, HEADER_H,
                                boxstyle='round,pad=0,rounding_size=10',
                                facecolor=accent, edgecolor='none', zorder=3))
    ax.add_patch(Rectangle((x0, y0 + h - HEADER_H), w, 13, facecolor=accent,
                           edgecolor='none', zorder=3))
    ax.text(x0 + w / 2, y0 + h - 21, title, ha='center', va='center',
            fontsize=12, fontweight='bold', color='white', zorder=4)
    ax.text(x0 + w / 2, y0 + h - 40, subtitle, ha='center', va='center',
            fontsize=9.2, color='white', alpha=0.93, zorder=4)


def inner(x0, y0, w, h):
    """Return the drawable rectangle of a card: (left, right, bottom, top)."""
    return x0 + PAD, x0 + w - PAD, y0 + PAD, y0 + h - HEADER_H - PAD


def rows(left, right, top, entries, accent, fontsize=9.6):
    """Stack of measurement rows: name on the left, measured figure on the right.

    Returns the y coordinate of the lowest row, so whatever follows can be
    placed relative to it instead of by a hard-coded offset.
    """
    y = top - ROW_H
    for label, value in entries:
        ax.add_patch(FancyBboxPatch((left, y), right - left, ROW_H,
                                    boxstyle='round,pad=0,rounding_size=6',
                                    facecolor=C['wash'], edgecolor=C['rule'],
                                    linewidth=0.8, zorder=4))
        ax.add_patch(Rectangle((left + 1.5, y + 4), 4, ROW_H - 8,
                               facecolor=accent, edgecolor='none', zorder=5))
        ax.text(left + 14, y + ROW_H / 2, label, ha='left', va='center',
                fontsize=fontsize, color=C['ink'], zorder=6)
        ax.text(right - 12, y + ROW_H / 2, value, ha='right', va='center',
                fontsize=fontsize, fontweight='bold', color=accent, zorder=6)
        y -= ROW_H + ROW_GAP
    return y + ROW_H + ROW_GAP


def note_box(left, right, bottom, height, lines, accent):
    """Tinted box closing a layer.

    Each line is (text, bold) or (text, bold, fontsize); lines are spread evenly
    inside the box, so no line can drift onto its border.
    """
    ax.add_patch(FancyBboxPatch((left, bottom), right - left, height,
                                boxstyle='round,pad=0,rounding_size=8',
                                facecolor=accent, alpha=0.10,
                                edgecolor=accent, linewidth=1.0, zorder=4))
    step = height / (len(lines) + 1)
    for i, line in enumerate(lines):
        text, bold = line[0], line[1]
        size = line[2] if len(line) > 2 else 9.5
        ax.text((left + right) / 2, bottom + height - (i + 1) * step, text,
                ha='center', va='center', fontsize=size,
                fontweight='bold' if bold else 'normal',
                color=accent if bold else C['grey'], zorder=6)


def flow_arrow(x0, x1, y, color):
    ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle='-|>',
                                 mutation_scale=18, linewidth=2.4,
                                 color=color, zorder=6, shrinkA=0, shrinkB=0))


# ==============================================================================
# HEADER
# ==============================================================================
ax.text(26, 530, 'One control stack, three robot vendors, one plant interface',
        ha='left', va='center', fontsize=17.5, fontweight='bold', color=C['ink'])
ax.text(26, 504, 'Compiler-enforced layer contracts turn a monolithic collaborative cell '
                 'into three independently testable layers, at a cost of '
                 f"{NUMBERS['arch_cost_ms']} ms per control cycle",
        ha='left', va='center', fontsize=11.3, color=C['grey'])
ax.add_patch(Rectangle((26, 490), W - 52, 2.2, facecolor=C['rule'],
                       edgecolor='none'))

LY, LH = 108, 366          # layer bottom and height

# ==============================================================================
# COLUMN 0 - Robot platforms
# ==============================================================================
RX, RW = 26, 168
ax.text(RX + RW / 2, LY + LH - 12, 'Robot Platforms', ha='center', va='center',
        fontsize=11.5, fontweight='bold', color=C['grey'])

platforms = [('Universal Robots UR5e', 'URScript / RTDE'),
             ('KUKA iiwa LBR', 'Fast Robot Interface'),
             ('ABB YuMi', 'Robot Web Services / EGM')]
for i, (name, proto) in enumerate(platforms):
    y = LY + 232 - i * 82
    ax.add_patch(FancyBboxPatch((RX, y), RW, 62,
                                boxstyle='round,pad=0,rounding_size=8',
                                facecolor=C['metal'], edgecolor=C['physical'],
                                linewidth=1.1, zorder=4))
    ax.text(RX + RW / 2, y + 39, name, ha='center', va='center', fontsize=10.2,
            fontweight='bold', color=C['ink'], zorder=6)
    ax.text(RX + RW / 2, y + 20, proto, ha='center', va='center', fontsize=9.2,
            color=C['grey'], zorder=6)
    flow_arrow(RX + RW + 6, RX + RW + 32, y + 31, C['physical'])

ax.text(RX + RW / 2, LY + 44, 'Adapter pattern', ha='center', va='center',
        fontsize=9.5, style='italic', color=C['grey'], zorder=6)

# ==============================================================================
# LAYER 1 - Physical abstraction
# ==============================================================================
L1X, L1W = 232, 258
layer(L1X, LY, L1W, LH, 'Physical Abstraction Layer',
      'Vendor-neutral interfaces  |  measured', C['physical'])
L, R, B, T = inner(L1X, LY, L1W, LH)

last = rows(L, R, T, [
    ('Code reuse', f"{NUMBERS['reuse_pct']}%"),
    ('Vendor-specific lines', f"{NUMBERS['loc_lo']}-{NUMBERS['loc_hi']}"),
    ('Port to KUKA / ABB', '18 h / 16 h'),
    ('Frame conversion', 'In the adapter'),
], C['physical'])

note_box(L, R, B, last - B - 16, [
    ('No vendor call reaches', False),
    ('the safety algorithms', False),
    ('Separation is enforced,', True),
    ('not merely documented', True),
], C['physical'])

flow_arrow(L1X + L1W + 6, L1X + L1W + 40, LY + LH / 2 - 26, C['control'])

# ==============================================================================
# LAYER 2 - Real-time control
# ==============================================================================
L2X, L2W = 536, 258
layer(L2X, LY, L2W, LH, 'Real-Time Control Layer',
      'Bounded-latency execution  |  measured', C['control'])
L, R, B, T = inner(L2X, LY, L2W, LH)

last = rows(L, R, T, [
    ('Barrier inference', f"{NUMBERS['cbf_ms']} / {NUMBERS['cbf_grad_ms']} ms"),
    ('Serial critical path', f"{NUMBERS['critical_path_ms']} ms"),
    ('Deadline misses', f"0 in {NUMBERS['blocks']} blocks"),
    ('Cost of the layering', f"+{NUMBERS['arch_cost_ms']} ms"),
], C['control'])

note_box(L, R, B, last - B - 16, [
    ('Lipschitz barrier for speed,', False),
    ('hard 150 mm geometric floor for safety', False),
    ('The layering costs 0.3 ms and', True),
    ('does not improve the tail', True),
], C['control'])

flow_arrow(L2X + L2W + 6, L2X + L2W + 40, LY + LH / 2 - 26, C['integration'])

# ==============================================================================
# LAYER 3 - Integration
# ==============================================================================
L3X, L3W = 840, 234
layer(L3X, LY, L3W, LH, 'Integration Layer',
      'Plant and MES connectivity  |  simulated', C['integration'])
L, R, B, T = inner(L3X, LY, L3W, LH)

last = rows(L, R, T, [
    ('OPC-UA read', f"{NUMBERS['opcua_ms']} ms"),
    ('Modbus TCP read', f"{NUMBERS['modbus_ms']} ms"),
    ('EtherCAT cycle', f"{NUMBERS['ethercat_ms']} ms"),
    ('REST / OpenAPI 3.0', f"{NUMBERS['api_median']} ms"),
], C['integration'], fontsize=9.4)

ax.text(R, last - 12, f"Medians; REST {NUMBERS['api_p95']} ms at 95th percentile",
        ha='right', va='center', fontsize=8.4, color=C['grey'], zorder=6)

note_box(L, R, B, last - B - 26, [
    ('PLC toolchains commissioned in', False),
    (f"{NUMBERS['plc_lo']}-{NUMBERS['plc_hi']} h  (measured)", True, 13.5),
    (f"Against {NUMBERS['plc_custom_lo']}-{NUMBERS['plc_custom_hi']} h", False),
    ("(author's estimate)", False),
], C['integration'])

# ==============================================================================
# FOOTER - reliability strip and scope statement
# ==============================================================================
ax.add_patch(FancyBboxPatch((26, 18), W - 52, 74,
                            boxstyle='round,pad=0,rounding_size=8',
                            facecolor=C['wash'], edgecolor=C['rule'],
                            linewidth=1.0, zorder=2))

# The fourth cell held an extrapolated 847 h MTBF in the first submission. It is
# withdrawn; what replaces it is the operator-intervention MTBF measured inside
# the observation window, with its exact Poisson interval.  R2: every cell now
# comes from the 200 h continuous run, so the strip no longer mixes the run with
# the fault-injection campaign.
stats = [(f"{NUMBERS['avail_pct']}%", 'Availability (simulated)'),
         (f"{NUMBERS['stress_h']} h", 'Simulated run'),
         (f"{NUMBERS['recovery_s']} s", 'Mean auto-recovery'),
         (f"{NUMBERS['mtbf_h']} h", f"Operator MTBF [{NUMBERS['mtbf_lo']}, {NUMBERS['mtbf_hi']}]")]
for i, (value, label) in enumerate(stats):
    x = 96 + i * 176
    ax.text(x, 68, value, ha='center', va='center', fontsize=15.5,
            fontweight='bold', color=C['ink'], zorder=6)
    ax.text(x, 48, label, ha='center', va='center', fontsize=8.8,
            color=C['grey'], zorder=6)
    if i:
        ax.add_patch(Rectangle((x - 88, 40), 1.4, 40, facecolor=C['rule'],
                               edgecolor='none', zorder=5))

ax.add_patch(Rectangle((790, 34), 1.6, 50, facecolor=C['rule'],
                       edgecolor='none', zorder=5))
ax.text(936, 74, 'Every figure obtained against vendor-conformant', ha='center',
        va='center', fontsize=9.0, color=C['ink'], zorder=6)
ax.text(936, 58, 'simulated interfaces. No physical robot, no safety', ha='center',
        va='center', fontsize=9.0, color=C['ink'], zorder=6)
ax.text(936, 42, 'hardware, no human participant. No SIL claimed.', ha='center',
        va='center', fontsize=9.0, color=C['ink'], zorder=6)

# ==============================================================================
# EXPORT
# ==============================================================================
# The file is written next to this script, in ./figures_ga/, so the run does not
# depend on the working directory and never tries to write to a protected
# location such as the root of a Windows drive.  It is then flattened from RGBA
# to RGB against white and tagged at 600 dpi, which is the form the editorial
# office receives.
out = OUT_DIR / 'GA_Electronics_4587969.png'
fig.savefig(out, dpi=DPI, facecolor='white')

with Image.open(out) as im:
    flat = Image.new('RGB', im.size, (255, 255, 255))
    flat.paste(im, mask=im.split()[3] if im.mode == 'RGBA' else None)
flat.save(out, dpi=(600, 600))

print(f'written: {out}  ({flat.width} x {flat.height} px, {flat.mode})')
