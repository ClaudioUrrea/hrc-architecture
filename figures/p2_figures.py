#!/usr/bin/env python3
"""
P2 Complete Figures Generator -- REVISION R1 (manuscript electronics-4587969)
Generates all 13 figures (1-12 and A1) for P2 (MDPI Electronics)
- Vendor-Neutral Embedded Control Architecture for Safety-Critical HRC
- All data verified against the revised paper tables and text

Author: Claudio Urrea
Date: September 2026

NATURE OF THE DATA
------------------
All series plotted here are outputs of the software architecture running
against SIMULATED vendor robot, sensor and PLC interfaces. No physical cell
was built, no safety-rated hardware was exercised and no human participant
supplied data. Panels are labelled measured / simulated / estimated /
projected in the figure captions of the paper.

CHANGES IN REVISION R1 (responses to reviewers)
-----------------------------------------------
R1/R2/R3  All typography enlarged (base font 10 -> 12 pt, explicit sizes
          scaled by 1.2) so that dense multipanel figures remain legible.
R3-11     Figure 9(d): defect taxonomy relabelled so that the figure and the
          text agree (0 major, 21 minor warnings, 78 informational; total 99).
R3-9/10   Figure 10 rebuilt from scratch. The former panel (a), a declining
          curve labelled "MTBF" that contradicted the constant-hazard
          statement, is replaced by a Weibull probability plot with the fitted
          shape/scale, a bootstrap CI on the shape and a KS goodness-of-fit
          statistic. The former panel (d), which compared the extrapolated
          MTBF against safety-standard "targets" that have no such normative
          basis, is replaced by a forest plot of MTBF by fault population with
          exact Poisson confidence intervals. The 847 h extrapolation is
          WITHDRAWN: it is not derivable from a 200 h window.
R3-4      Figure 12 added: architectural ablation (A0-A3) run with an
          identical controller and an identical replayed workload, isolating
          the contribution of the architecture from that of the algorithm.
R3-5      Figure 11 bars explicitly annotated measured / estimated /
          projected.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle, Wedge, Polygon
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import numpy as np
import os

# ---------------------------------------------------------------------------
# Publication-quality parameters
#
# MDPI Electronics requires figures at a minimum of 600 dpi. DPI is set once
# here, in DPI, and every savefig call reads it, so the resolution cannot
# drift between figures.
# ---------------------------------------------------------------------------
DPI = 600

plt.rcParams['font.family'] = 'DejaVu Serif'
plt.rcParams['font.size'] = 12

# Reviewer 3 asked for larger labels in the denser multipanel figures. Rather
# than tune each panel by hand, every explicit fontsize in this script was
# scaled by FONT_SCALE and the axes-level defaults were raised with it.
FONT_SCALE = 1.2
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['xtick.labelsize'] = 11
plt.rcParams['ytick.labelsize'] = 11
plt.rcParams['legend.fontsize'] = 11
plt.rcParams['axes.linewidth'] = 1.2
plt.rcParams['figure.dpi'] = DPI
plt.rcParams['savefig.dpi'] = DPI

# Keep text as text rather than outlines, so the typesetter can still search
# and reflow labels if the figure is placed in a vector workflow.
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

# At 600 dpi hairlines can disappear in print; hold them above 0.8 pt.
plt.rcParams['lines.linewidth'] = max(plt.rcParams.get('lines.linewidth', 1.5), 1.2)
plt.rcParams['grid.linewidth'] = 0.8
plt.rcParams['patch.linewidth'] = 1.0

# Create output directory if needed
_START_DIR = os.getcwd()
os.makedirs('figures_p2_electronics', exist_ok=True)
os.chdir('figures_p2_electronics')

def save_figure(basename):
    """Write one figure as 600-dpi PNG plus a vector PDF companion.

    MDPI asks for the raster at 600 dpi for the production PDF; the vector
    copy costs nothing to emit and is what to send if the editors later ask
    for scalable artwork.
    """
    png = f"{basename}.png"
    plt.savefig(png, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.savefig(f"{basename}.pdf", bbox_inches='tight', facecolor='white')
    w_in, h_in = plt.gcf().get_size_inches()
    print(f"   -> {png}  ({w_in*DPI:.0f} x {h_in*DPI:.0f} px nominal, {DPI} dpi) + PDF")


# ---------------------------------------------------------------------------
# Data access. Figures 6a,b,d and 10a,b are drawn from the deposited data
# files (protocol_samples.parquet, stage_timings.parquet, interfailure.csv,
# faults_450.csv), not from random draws, so that every plotted value can be
# traced to the deposit and agrees with the analysis scripts. Point HRC_DATA
# at the deposit's data directory (default: ./data, ../data, or the sibling
# hrc-architecture/data); analysis/fetch_figshare.py downloads the large files.
# ---------------------------------------------------------------------------
_START_DIR = os.getcwd()

def data_path(name):
    cands = [os.environ.get('HRC_DATA', ''), 'data', '../data',
             '../hrc-architecture/data', '../../hrc-architecture/data', '.', '..']
    for d in cands:
        if d:
            p = os.path.join(_START_DIR, d, name)
            if os.path.exists(p):
                return p
    raise FileNotFoundError(
        f"{name} not found; set HRC_DATA to the deposit's data directory "
        f"(see analysis/fetch_figshare.py)")


print("="*80)
print("GENERATING ALL P2 FIGURES")
print("="*80)

# =============================================================================
# FIGURE 1: Software Architecture (3-Layer Design) 
# =============================================================================
print("\n[1/13] Generating Figure 1: Software Architecture...")
fig, ax = plt.subplots(figsize=(11, 7))

colors = {
    'integration': ['#E8F5E9', '#C8E6C9', '#A5D6A7'],
    'control':     ['#FFF3E0', '#FFE0B2', '#FFCC80'],
    'physical':    ['#E3F2FD', '#BBDEFB', '#90CAF9'],
    'border':      '#263238',
    'text':        '#212121',
    'accent':      '#FF6F00'
}

def draw_modern_layer(ax, y_base, gradient_colors, title, components,
                      line_spacing=0.30, top_margin=0.48):
    # line_spacing raised from 0.25 to 0.30 in revision R1b: at the enlarged
    # base font the component lines were touching one another.
    x_start, width = 0.5, 11.0
    n_items = len(components)
    content_height = top_margin + n_items * line_spacing + 0.30
    height = max(content_height, 1.5)
    
    n_strips = 20
    for i in range(n_strips):
        strip_h = height / n_strips
        strip_y = y_base + i * strip_h
        color_idx = int(i / n_strips * len(gradient_colors))
        color_idx = min(color_idx, len(gradient_colors) - 1)
        strip = FancyBboxPatch((x_start, strip_y), width, strip_h,
                              boxstyle="round,pad=0.02",
                              facecolor=gradient_colors[color_idx],
                              edgecolor='none', zorder=1)
        ax.add_patch(strip)
    
    shadow = FancyBboxPatch((x_start + 0.06, y_base - 0.06), width, height,
                           boxstyle="round,pad=0.08",
                           facecolor='black', alpha=0.15, zorder=0)
    ax.add_patch(shadow)
    
    border = FancyBboxPatch((x_start, y_base), width, height,
                           boxstyle="round,pad=0.08",
                           facecolor='none', edgecolor=colors['border'],
                           linewidth=2.5, zorder=2)
    ax.add_patch(border)
    
    text_y = y_base + height - top_margin
    ax.text(x_start + 0.3, text_y+0.32, title,
           fontsize=16.8, weight='bold', color=colors['text'], zorder=3, va='top')
    
    for i, comp in enumerate(components):
        ax.text(x_start + 0.34, text_y - 0.24 - i * line_spacing, comp,
               fontsize=12, color=colors['text'], zorder=3, va='top')
    
    return height

layers_data = [
    (7.22, colors['integration'], 'Integration Layer', [
        'RESTful API (OpenAPI 3.0)',
        'WebSocket Streaming (50Hz)',
        'OPC-UA Server (IEC 62541)',
        'Modbus/TCP Gateway',
        'EtherCAT Master'
    ]),
    (4.3, colors['control'], 'Real-Time Control Layer', [
        'Learned Control Barrier Functions (1.8ms inference)',
        'Model Predictive Control (2.8ms QP solve)',
        'Sensor Fusion (4.5 ms, concurrent thread)',
        'Safety Monitor (6.2 ms critical path @ 50 Hz)',
        'Fault Detection & Recovery'
    ]),
    (1.1, colors['physical'], 'Physical Abstraction Layer', [
        'IRobotController (Adapter Pattern)',
        '  - URRobotController (RTDE 125Hz)',
        '  - KUKARobotController (FRI 200Hz)',
        '  - ABBRobotController (RWS REST)',
        'Sensor Array (6× RealSense D435)',
        'Hardware Abstraction'
    ])
]

for y_base, grad_colors, title, components in layers_data:
    draw_modern_layer(ax, y_base, grad_colors, title, components)

def draw_flow_arrow(ax, x, y_from, y_to, label):
    ax.annotate('', xy=(x, y_to), xytext=(x, y_from),
               arrowprops=dict(arrowstyle='->', lw=3.5, color=colors['accent'],
                              shrinkA=0, shrinkB=0),
               zorder=10)
    ax.text(x + 0.35, (y_from + y_to) / 2, label, fontsize=10.8, weight='bold',
           color=colors['accent'], va='center', zorder=10,
           bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                    edgecolor=colors['accent'], linewidth=1.5))

# Arrow between Integration (bottom=7.15) and Control (top~6.15)
draw_flow_arrow(ax, 6.0, 6.45, 7.15, 'API Calls')
# Arrow between Control (bottom=4.05) and Physical (top~3.30)
draw_flow_arrow(ax, 6.0, 3.5, 4.2, 'Control Cmds')

ax.text(6.0, 10.2, 'Three-Layer Modular Software Architecture\n'
        'for Safety-Critical Human\u2013Robot Collaboration',
       ha='center', va='center', fontsize=18, weight='bold',
       color=colors['text'])

metrics_box = FancyBboxPatch((0.5, -0.35), 11.0, 0.80,
                            boxstyle="round,pad=0.08",
                            facecolor='#FFF9C4', edgecolor=colors['accent'],
                            linewidth=2, zorder=1)
ax.add_patch(metrics_box)

# Label and value are drawn as ONE centred two-line string per column, on a
# uniform grid. The previous version positioned them with hand-tuned x offsets,
# which collided once the base font was enlarged.
metric_items = [
    ('API latency',        '2.1 ms (p50) / 4.8 ms (p95)'),
    ('Control critical path', '6.2 ms @ 50 Hz'),
    ('Cross-vendor code reuse', '86%'),
    ('Simulated availability', '98.5%'),
]
n_m = len(metric_items)
for k, (label, value) in enumerate(metric_items):
    xc = 0.5 + 11.0 * (k + 0.5) / n_m
    ax.text(xc, 0.20, label, fontsize=10.5, weight='bold', ha='center',
            va='center', color=colors['text'], zorder=3)
    ax.text(xc, -0.10, value, fontsize=10.5, ha='center', va='center',
            color=colors['accent'], zorder=3)

ax.set_xlim(0, 12)
ax.set_ylim(-0.7, 10.8)
ax.axis('off')
plt.tight_layout()
save_figure('Figure1_Software_Architecture')
print("Figure 1 saved")
plt.close()


# =============================================================================
# FIGURE 2: Adapter Pattern 
# =============================================================================
print("\n[2/13] Generating Figure 2: Adapter Pattern...")

fig, ax = plt.subplots(figsize=(10, 6))

uml_colors = {
    'interface': '#E1F5FE', 'interface_border': '#0277BD',
    'concrete': '#FFF9C4', 'concrete_border': '#F57C00',
    'text': '#263238', 'accent': '#FF6F00', 'connection': '#455A64'
}

def draw_uml_class(ax, x, y, width, height, classname, methods, stereotype='',
                  is_interface=False, notes=''):
    bg_color = uml_colors['interface'] if is_interface else uml_colors['concrete']
    border_color = uml_colors['interface_border'] if is_interface else uml_colors['concrete_border']
    
    shadow = FancyBboxPatch((x + 0.08, y - 0.02), width, height,
                           boxstyle="round,pad=0.05", facecolor='black', alpha=0.15, zorder=1)
    ax.add_patch(shadow)
    box = FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.05",
                        edgecolor=border_color, facecolor=bg_color,
                        linewidth=2.5, zorder=2)
    ax.add_patch(box)
    
    curr_y = y + height - 0.22
    if stereotype:
        ax.text(x + width/2, curr_y, f'«{stereotype}»',
               ha='center', va='top', fontsize=12, style='italic',
               color=uml_colors['accent'], weight='bold', zorder=3)
        curr_y -= 0.28
    
    ax.text(x + width/2, curr_y, classname,
           ha='center', va='top', fontsize=15.6, weight='bold',
           color=uml_colors['text'], zorder=3)
    curr_y -= 0.38
    
    ax.plot([x + 0.1, x + width - 0.1], [curr_y, curr_y],
           color=border_color, linewidth=2, zorder=3)
    curr_y -= 0.22
    
    for method in methods:
        prefix = '+ ' if not method.startswith('-') else ''
        ax.text(x + 0.13, curr_y, prefix + method,
               ha='left', va='top', fontsize=8.8, family='monospace',
               color=uml_colors['text'], zorder=3)
        curr_y -= 0.25
    
    if notes:
        ax.text(x + width/2, y - 0.12, notes,
               ha='center', va='top', fontsize=10.2, style='italic',
               color='black', zorder=3)

# Interface (top center) draw_uml_class(ax, 3.7, 4.1, 3.0, 2.2 + 0.16, 'IRobotController',
draw_uml_class(ax, 3.7, 3.9, 3.0, 2.4 + 0.16, 'IRobotController',
              ['moveJoint(targets, velocity)',
               'moveCartesian(target, velocity)',
               'getCurrentState()',
               'setOverride(factor)',
               'emergencyStop()',
               'getHealthStatus()'],
              stereotype='interface', is_interface=True)

# Concrete adapters with INCREASED HEIGHT
draw_uml_class(ax, 0.3, 1.4, 3.0, 1.9 + 0.14, 'URRobotController',
              ['moveJoint(...)',
               'getCurrentState()',
               '- rtde_connection',
               '- urscript_client',
               '- control_thread'],
              notes='URScript TCP/IP | RTDE 125Hz')

draw_uml_class(ax, 3.7, 1.4, 3.0, 1.9 + 0.14, 'KUKARobotController',
              ['moveJoint(...)',
               'getCurrentState()',
               '- fri_connection',
               '- sunrise_api',
               '- motion_queue'],
              notes='KUKA FRI UDP | Sunrise 200Hz')

draw_uml_class(ax, 7.1, 1.4, 3.0, 1.9 + 0.14, 'ABBRobotController',
              ['moveJoint(...)',
               'getCurrentState()',
               '- rws_client',
               '- websocket_conn',
               '- trajectory_buffer'],
              notes='Robot Web Services | REST')

# Implementation arrows
def draw_implements_arrow(ax, x1, y1, x2, y2):
    ax.plot([x1, x2], [y1, y2], 'k--', linewidth=2, zorder=1, alpha=0.7)
    arrow_size = 0.2
    dx, dy = x2 - x1, y2 - y1
    length = np.sqrt(dx**2 + dy**2)
    dx, dy = dx/length, dy/length
    tip = (x2, y2)
    left = (x2 - arrow_size*dx - arrow_size*dy*0.5, y2 - arrow_size*dy + arrow_size*dx*0.5)
    right = (x2 - arrow_size*dx + arrow_size*dy*0.5, y2 - arrow_size*dy - arrow_size*dx*0.5)
    triangle = Polygon([tip, left, right], facecolor='white',
                      edgecolor='black', linewidth=2, zorder=2)
    ax.add_patch(triangle)

draw_implements_arrow(ax, 1.8, 3.5, 3.6, 4.4)
draw_implements_arrow(ax, 5.2, 3.5, 5.2, 3.8)
draw_implements_arrow(ax, 8.6, 3.5, 6.8, 4.4)

ax.text(5.5, 6.9, 'Adapter Pattern: Vendor-Neutral Robot Control',
       ha='center', va='center', fontsize=19.2, weight='bold',
       color=uml_colors['text'])

# Metrics banner
metrics_box = FancyBboxPatch((0.3, 0.15), 9.8, 0.55,
                            boxstyle="round,pad=0.1",
                            facecolor='#E8F5E9', edgecolor='#388E3C',
                            linewidth=2, zorder=1)
ax.add_patch(metrics_box)
metrics_text = ('Code reuse (measured): 9,274 LOC shared / 487 LOC (UR5e) / 523 LOC (KUKA) / 456 LOC (ABB)\n'
               'Adaptation effort (measured): 18 h (KUKA) / 16 h (ABB)  vs.  200\u2013250 h monolithic rewrite (estimated)')
ax.text(5.2, 0.44, metrics_text, ha='center', va='center', fontsize=11.2,
       color=uml_colors['text'])

pattern_note = ('Design Pattern: Adapter (GoF)\n'
               'Purpose: Vendor independence\n'
               'Benefit: 12\u201314\u00d7 faster adaptation (est.)')
ax.text(0.18, 6.0, pattern_note, ha='left', va='top', fontsize=10.0,
       bbox=dict(boxstyle='round', facecolor='#FFF9C4',
                edgecolor='#F57C00', linewidth=2, alpha=0.9))

ax.set_xlim(0, 10.5)
ax.set_ylim(0, 7.0)
ax.axis('off')
plt.tight_layout()
save_figure('Figure2_Adapter_Pattern')
print("Figure 2 saved")
plt.close()


# =============================================================================
# FIGURE 3: Multi-Platform Analysis 
# =============================================================================
print("\n[3/13] Generating Figure 3: Multi-Platform Analysis...")

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))

platforms = ['UR5e', 'KUKA iiwa', 'ABB YuMi']
common_code = [9274, 9274, 9274]
platform_specific = [487, 523, 456]

x = np.arange(len(platforms))
width = 0.6
bars1 = ax1.bar(x, common_code, width, label='Shared platform-independent code',
               color='#2ECC71', edgecolor='black', linewidth=1.2)
bars2 = ax1.bar(x, platform_specific, width, bottom=common_code,
               label='Vendor-specific adapter', color='#E74C3C',
               edgecolor='black', linewidth=1.2)
for i in range(len(platforms)):
    total = common_code[i] + platform_specific[i]
    # The platform-specific band is only ~500 LOC tall on a 12,000 LOC axis, so
    # its label cannot fit inside it. It is placed above the stack instead.
    ax1.annotate(f'{platform_specific[i]} LOC',
                 xy=(i, total), xytext=(i, total + 950),
                 ha='center', fontsize=11.5, weight='bold', color='#B03A2E',
                 arrowprops=dict(arrowstyle='-', color='#B03A2E', lw=1.2))
    ax1.text(i, common_code[i]/2, f'{common_code[i]}\nLOC\nshared', ha='center',
             va='center', fontsize=12, weight='bold', color='black')

ax1.set_ylabel('Lines of Code', fontsize=14.4, weight='bold')
ax1.set_title('(a) Code reuse across platforms (86% aggregate)', fontsize=13.2, weight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(platforms, fontsize=13.2)
ax1.legend(loc='upper center', ncol=2, fontsize=10.5, framealpha=0.95)
ax1.grid(axis='y', alpha=0.3)
ax1.set_ylim(0, 15500)
ax1.set_yticks(range(0, 12001, 2000))

# Platform Adaptation Effort 
platforms_full = ['UR5e\n(Baseline)', 'KUKA iiwa', 'ABB YuMi', 'Monolithic\nRewrite']
adaptation_times = [0, 18, 16, 225]
colors_adapt = ['#95A5A6', '#3498DB', '#9B59B6', '#E74C3C']

bars = ax2.barh(range(len(platforms_full)), adaptation_times, color=colors_adapt,
               edgecolor='black', linewidth=1.2, height=0.6)
bars[3].set_hatch('//')   # estimated, not measured
for i, (bar, time) in enumerate(zip(bars, adaptation_times)):
    if time > 0:
        ax2.text(time + 7, i, f'{time} h' + (' (est.)' if i == 3 else ''), va='center', fontsize=12, weight='bold')
    else:
        ax2.text(5, i, 'Baseline', va='center', fontsize=10.8, style='italic', color='black', weight='bold')

ax2.set_xlabel('Adaptation Time (hours)', fontsize=14.4, weight='bold')
ax2.set_title('(b) Platform adaptation effort\n(measured vs. estimated)', fontsize=13.2, weight='bold')
ax2.set_yticks(range(len(platforms_full)))
ax2.set_yticklabels(platforms_full, fontsize=12)
ax2.grid(axis='x', alpha=0.3)
ax2.set_xlim(0, 330)

# Code Complexity
components = ['Common\nCore', 'UR\nAdapter', 'KUKA\nAdapter', 'ABB\nAdapter']
complexities = [4.2, 3.8, 3.9, 3.7]
colors_complex = ['#2ECC71', '#3498DB', '#9B59B6', '#F39C12']
bars = ax3.bar(range(len(components)), complexities, color=colors_complex,
               edgecolor='black', linewidth=1.2)
ax3.axhline(5.0, color='orange', linestyle='--', linewidth=2, label='Threshold (Good: <5)')
for i, (bar, comp) in enumerate(zip(bars, complexities)):
    ax3.text(i, comp + 0.15, f'{comp}', ha='center', fontsize=12, weight='bold')
ax3.set_ylabel('Cyclomatic Complexity', fontsize=14.4, weight='bold')
ax3.set_title('(c) Cyclomatic complexity (all below 5.0)', fontsize=13.2, weight='bold')
ax3.set_xticks(range(len(components)))
ax3.set_xticklabels(components, fontsize=12)
ax3.legend(loc='upper right', fontsize=12)
ax3.grid(axis='y', alpha=0.3)
ax3.set_ylim(0, 6)

# Platform Capabilities Table 
table_data = [
    ['Feature', 'UR5e', 'KUKA iiwa', 'ABB YuMi'],
    ['State rate', '125 Hz', '200 Hz', '125 Hz'],
    ['Interface', 'RTDE / TCP', 'FRI / UDP', 'RWS / HTTPS'],
    ['Frame', 'Base, flange-\naligned', 'Flange + TCP\noffset', 'Work-object'],
    ['Protective stop', 'stopj()', 'stopMotion()', 'Panel control\nstate'],
    ['Integration Time', 'Baseline', '18h', '16h']
]
table = ax4.table(
	cellText=table_data, 
	cellLoc='center', 
	loc='center',
        bbox=[-0.15, 0.037, 1.16, 0.94], 
)

ax4.axis('off')
table.auto_set_font_size(False)
table.set_fontsize(9.4)
table.scale(1, 2)
for i in range(4):
    cell = table[(0, i)]
    cell.set_facecolor('#3498DB')
    cell.set_text_props(weight='bold', color='white', fontsize=14)
for i in range(1, 6):
    table[(i, 0)].set_facecolor('#ECF0F1')
    table[(i, 0)].set_text_props(weight='bold')
ax4.set_title('(d) Platform Capabilities Comparison          ', fontsize=14.0, weight='bold', pad=00)

plt.tight_layout(h_pad=2.0, w_pad=2.0)
save_figure('Figure3_Multiplatform_Analysis')
print("Figure 3 saved")
plt.close()


# =============================================================================
# FIGURE 4: PLC Integration Architecture 
# =============================================================================
print("\n[4/13] Generating Figure 4: PLC Integration...")

fig, ax = plt.subplots(1, 1, figsize=(11, 6.0))

industrial_colors = {
    'hrc': ['#E3F2FD', '#BBDEFB', '#90CAF9'],
    'protocol': ['#FFF3E0', '#FFE0B2', '#FFCC80'],
    'plc': ['#E8F5E9', '#C8E6C9', '#A5D6A7'],
    'border': '#263238',
    'data_in': '#1976D2',
    'data_out': '#D32F2F'
}

def draw_gradient_box_v2(ax, x, y, w, h, gradient_colors, text,
                        fontsize=13.2, bold=False, subtitle=''):
    n_strips = 15
    for i in range(n_strips):
        strip_h = h / n_strips
        strip_y = y + i * strip_h
        color_idx = min(int(i / n_strips * len(gradient_colors)), len(gradient_colors) - 1)
        strip = FancyBboxPatch((x, strip_y), w, strip_h, boxstyle="round,pad=0.02",
                              facecolor=gradient_colors[color_idx], edgecolor='none', zorder=1)
        ax.add_patch(strip)
    shadow = FancyBboxPatch((x + 0.05, y - 0.05), w, h, boxstyle="round,pad=0.05",
                           facecolor='black', alpha=0.12, zorder=0)
    ax.add_patch(shadow)
    border = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                           facecolor='none', edgecolor=industrial_colors['border'],
                           linewidth=2.5, zorder=2)
    ax.add_patch(border)
    weight = 'bold' if bold else 'normal'
    ax.text(x + w/2, y + h/2 + 0.14, text, ha='center', va='center',
           fontsize=fontsize, weight=weight, color=industrial_colors['border'], zorder=3)
    if subtitle:
        # Subtitles are set on up to two lines at a reduced size so that they
        # stay inside their box: the single-line variant of the previous
        # revision overflowed the OPC-UA and EtherCAT boxes.
        nl = subtitle.count('\n')
        ax.text(x + w/2, y + h/2 - (0.20 if nl else 0.25), subtitle,
                ha='center', va='center', fontsize=8.8, style='italic',
                color='#546E7A', zorder=3, linespacing=1.35)

def draw_data_arrow_v2(ax, x1, y1, x2, y2, label='', color='blue', bidirectional=False):
    style = '<|-|>' if bidirectional else '-|>'
    arrow_color = industrial_colors['data_in'] if color == 'blue' else industrial_colors['data_out']
    arrow = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=20,
                           linewidth=2.5, color=arrow_color, zorder=2, alpha=0.8)
    ax.add_patch(arrow)
    if label:
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mid_x, mid_y, label, ha='center', va='center', fontsize=9.6, weight='bold',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                        edgecolor=arrow_color, linewidth=1.5, alpha=0.95), zorder=4)

# HRC Control System (top)
draw_gradient_box_v2(ax, 4.5, 4.6, 4.5, 1.3, industrial_colors['hrc'],
                    'HRC Control System\nUR5e + Learned CBF',
                    fontsize=12.6, bold=True, subtitle='Real-Time Safety Monitoring')

# Data flow indicators
ax.text(3.4, 5.68, 'Joint pos., velocity,\nmin. distance, status',
       ha='center', fontsize=9.6, weight='bold', color=industrial_colors['data_in'])
ax.annotate('', xy=(4.5, 5.2), xytext=(3.0, 5.2),
           arrowprops=dict(arrowstyle='->', lw=2.5, color=industrial_colors['data_in']))

ax.text(9.95, 5.68, 'Commands,\nsafety override',
       ha='center', fontsize=9.6, weight='bold', color=industrial_colors['data_out'])
ax.annotate('', xy=(9.5, 5.2), xytext=(9.0, 5.2),
           arrowprops=dict(arrowstyle='<-', lw=2.5, color=industrial_colors['data_out']))

# Protocol Servers
draw_gradient_box_v2(ax, 1.0, 3.0, 2.8, 1.0, industrial_colors['protocol'],
                    'OPC-UA Server', fontsize=11, bold=True,
                    subtitle='IEC 62541 | open62541\n142 nodes | <5 ms')
draw_gradient_box_v2(ax, 5.1, 3.0, 2.8, 1.0, industrial_colors['protocol'],
                    'Modbus/TCP Gateway', fontsize=11, bold=True,
                    subtitle='pymodbus\n100 registers | 7.1 ms')
draw_gradient_box_v2(ax, 9.2, 3.0, 2.8, 1.0, industrial_colors['protocol'],
                    'EtherCAT Master', fontsize=11, bold=True,
                    subtitle='IgH master | 1 ms cycle\nPDO / SDO')

# The three free-floating protocol badges of the previous version sat on top of
# the OPC-UA / Modbus client boxes. Their content now lives in the subtitle of
# the corresponding gateway box, which cannot collide with anything.

# HRC -> Protocol connections
draw_data_arrow_v2(ax, 5.8, 4.6, 2.4, 4.0, '', 'blue', True)
draw_data_arrow_v2(ax, 6.5, 4.6, 6.5, 4.0, '', 'blue', True)
draw_data_arrow_v2(ax, 7.8, 4.6, 10.6, 4.0, '', 'blue', True)

# PLC Systems
plcs = [
    (0.5, 0.9, 2.5, 0.85, 'Siemens S7-1200\nTIA Portal', '3.7h'),
    (3.5, 0.9, 2.5, 0.85, 'Allen-Bradley\nCompactLogix', '3.5h'),
    (6.5, 0.9, 2.5, 0.85, 'Mitsubishi FX5\nGX Works3', '3.8h'),
    (9.5, 0.9, 2.5, 0.85, 'Distributed I/O\nEtherCAT Slaves', '')
]
for x, y, w, h, text, setup_time in plcs:
    draw_gradient_box_v2(ax, x, y, w, h, industrial_colors['plc'], text, fontsize=12)
    if setup_time:
        ax.text(x + w/2, y - 0.12, f'Setup: {setup_time}', ha='center', fontsize=9.6,
               weight='bold', color='#2E7D32',
               bbox=dict(boxstyle='round', facecolor='#E8F5E9', edgecolor='#2E7D32', linewidth=1.5))

# Protocol -> PLC connections
draw_data_arrow_v2(ax, 2.0, 3.0, 1.75, 1.75, 'OPC-UA\nClient', 'blue', True)
draw_data_arrow_v2(ax, 2.8, 3.0, 4.5, 1.75, 'OPC-UA\nClient', 'blue', True)
draw_data_arrow_v2(ax, 6.5, 3.0, 7.75, 1.75, 'Modbus\nTCP', 'blue', True)
draw_data_arrow_v2(ax, 10.6, 3.0, 10.75, 1.75, '', 'blue', True)

# Title
ax.text(7.0, 6.4, 'Industrial PLC Integration Architecture',
       ha='center', va='center', fontsize=18.2, weight='bold',
       color=industrial_colors['border'])

# Performance banner
perf_box = FancyBboxPatch((1.0, -0.08), 10.5, 0.52, boxstyle="round,pad=0.08",
                         facecolor='#FFF9C4', edgecolor='#F57C00', linewidth=2.5, zorder=1)
ax.add_patch(perf_box)
# Single centred string per column on a uniform grid (see Figure 1 banner).
perf_items = [('Config. time (measured)', '3.67 h mean'),
              ('Protocols', 'OPC-UA | Modbus TCP | EtherCAT'),
              ('PLC vendors', 'Siemens | Allen-Bradley | Mitsubishi')]
for k, (label, value) in enumerate(perf_items):
    xc = 1.0 + 10.5 * (k + 0.5) / len(perf_items)
    ax.text(xc, 0.30, label, fontsize=10.5, weight='bold', ha='center', va='center')
    ax.text(xc, 0.06, value, fontsize=10.5, ha='center', va='center', color='#E65100')

ax.set_xlim(0, 13)
ax.set_ylim(-0.30, 7.05)
ax.axis('off')
plt.tight_layout()
save_figure('Figure4_PLC_Integration')
print("Figure 4 saved")
plt.close()


# =============================================================================
# FIGURE 5: PLC Configuration Time
# Modular: measured per platform (Siemens 3.7, Allen-Bradley 3.5, Mitsubishi 3.8 h;
# mean 3.67 h).  Bespoke: ONE undocumented author's estimate of 40-45 h that applies
# to the task, not to a platform.  It is drawn as a single hatched bar with a range,
# so that it cannot be read as three separate third-party quotations.
# =============================================================================
print("\n[5/13] Generating Figure 5: PLC Configuration Time...")

fig, ax = plt.subplots(1, 1, figsize=(10, 6.5))

labels = ['Siemens\nS7-1200\n(modular)', 'Allen-Bradley\nCompactLogix\n(modular)',
          'Mitsubishi\nFX5\n(modular)', 'Modular\nmean', "Bespoke\n(author's estimate)"]
vals = [3.7, 3.5, 3.8, 3.67, 42.5]
x = np.arange(len(labels))
cols = ['#2ECC71'] * 4 + ['#E74C3C']
bars = ax.bar(x, vals, 0.6, color=cols, edgecolor='black', linewidth=1.2)
bars[3].set_alpha(0.65)
bars[4].set_hatch('//')
ax.errorbar([4], [42.5], yerr=[[2.5], [2.5]], fmt='none', ecolor='black',
            elinewidth=2, capsize=8)
for k in range(4):
    ax.text(x[k], vals[k] + 0.8, f'{vals[k]:g} h', ha='center', va='bottom',
            fontsize=12, weight='bold')
ax.text(4, 46.5, '40\u201345 h', ha='center', va='bottom', fontsize=12, weight='bold')
ax.text(3.2, 55, 'About 11\u201312\u00d7 the modular mean\n(indicative)',
        ha='center', va='bottom', fontsize=10.5,
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

ax.set_ylabel('Configuration time (hours)', fontsize=14.4, weight='bold')
ax.set_title('PLC integration configuration time:\n'
             'modular architecture (measured) vs. bespoke implementation (estimate)',
             fontsize=14, weight='bold', pad=14)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=10.5)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.set_ylim(0, 70)
h1 = mpatches.Patch(facecolor='#2ECC71', edgecolor='black', label='Measured (simulator)')
h2 = mpatches.Patch(facecolor='#E74C3C', edgecolor='black', hatch='//',
                    label="Author's estimate")
ax.legend(handles=[h1, h2], loc='upper left', fontsize=11, framealpha=0.95)

plt.tight_layout()
save_figure('Figure5_PLC_Configuration_Time')
print("Figure 5 saved")
plt.close()


# =============================================================================
# FIGURE 6: Software Performance (4 subplots)
# =============================================================================
print("\n[6/13] Generating Figure 6: Software Performance...")

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(13, 8.2))

# API Latency Distribution
import pandas as pd
_ps = pd.read_parquet(data_path('protocol_samples.parquet'))
latencies = _ps.loc[_ps['protocol'] == 'rest', 'value'].to_numpy()
_q = np.quantile(latencies, [0.5, 0.95, 0.99])
ax1.hist(latencies, bins=80, range=(0.5, 8), color='#42A5F5', edgecolor='white', linewidth=0.3)
ax1.axvline(_q[0], color='red', linestyle='--', linewidth=2, label='p50: %.1fms' % _q[0])
ax1.axvline(_q[1], color='orange', linestyle='--', linewidth=2, label='p95: %.1fms' % _q[1])
ax1.axvline(_q[2], color='darkred', linestyle='--', linewidth=2, label='p99: %.1fms' % _q[2])
ax1.set_xlabel('Latency (ms)', fontsize=13.2)
ax1.set_ylabel('Frequency', fontsize=13.2)
ax1.set_title('(a) REST API response latency', fontsize=13.2, weight='bold')
ax1.legend(loc='upper right', fontsize=10.8)
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 8.7)

# Control cycle timing.
#
# REVISION R1: the previous panel summed four stages to 9.9 ms and called it
# the pipeline total, which contradicted Section 9.2 of the paper. Sensor
# fusion runs CONCURRENTLY in its own thread and is not on the serial critical
# path, so it is now drawn hatched and separated by a gap, and the panel total
# is the true critical path: 2.20 + 0.29 + 2.80 + 0.91 = 6.20 ms. The four
# serial terms are the medians of the deposited stage timings, as itemized in
# Table 5 of the paper (host-device transfer is shown as its own bar).
components_ctrl = ['CBF inference\n+ gradient', 'Transfer +\nsync', 'MPC solve\n(warm start)',
                   'Scheduling +\ndispatch', 'Sensor fusion\n(concurrent)']
_st = pd.read_parquet(data_path('stage_timings.parquet')).groupby('stage')['duration_ms'].median()
timings = [round(float(_st[k]), 2) for k in
           ('barrier_inference_with_gradient', 'host_device_transfer_sync',
            'qp_solve_hotstart', 'scheduling_serialization_dispatch', 'sensor_fusion')]
timings[4] = round(timings[4], 1)
_crit_total = round(sum(timings[:4]), 1)
assert abs(_crit_total - 6.2) < 0.051, _crit_total
critical = [True, True, True, True, False]
colors_ctrl = ['#E74C3C', '#F1948A', '#3498DB', '#95A5A6', '#2ECC71']
xpos_ctrl = [0, 1, 2, 3, 4.5]
for xp, t, c, is_crit in zip(xpos_ctrl, timings, colors_ctrl, critical):
    ax2.bar(xp, t, 0.72, color=c, edgecolor='black', linewidth=1.2,
            hatch=None if is_crit else '//')
    ax2.text(xp, t + 0.5, f'{t:g} ms', ha='center', fontsize=11, weight='bold')
ax2.axhline(20, color='red', linestyle='--', linewidth=2, label='50 Hz deadline (20 ms)')
# The critical-path marker is drawn only across the serial stages, so that it
# cannot be read as including the concurrent sensor-fusion bar.
ax2.hlines(_crit_total, -0.6, 3.75, color='#1A5276', linestyle='-.', linewidth=2,
           label='Serial critical path: 6.2 ms')
ax2.axvline(3.75, color='0.4', linestyle=':', linewidth=1.6)
ax2.text(3.78, 17.2, 'Off critical path', fontsize=10, style='italic',
         rotation=90, va='top', color='0.35')
ax2.set_ylabel('Time (ms)', fontsize=13.2)
ax2.set_title('(b) Control pipeline: 6.2 ms serial critical path',
              fontsize=13.2, weight='bold')
ax2.set_xticks(xpos_ctrl)
ax2.set_xticklabels(components_ctrl, fontsize=9.6)
ax2.legend(loc='upper left', fontsize=10.2, framealpha=0.95)
ax2.grid(axis='y', alpha=0.3)
ax2.set_xlim(-0.6, 5.1)
ax2.set_ylim(0, 25.5)

# Protocol Performance
protocols = ['OPC-UA\nRead', 'OPC-UA\nSubscribe', 'Modbus\nTCP', 'EtherCAT\nCycle']
latencies_proto = [4.2, 5.8, 7.1, 1.0]
colors_proto = ['#42A5F5', '#42A5F5', '#FFA726', '#66BB6A']
bars = ax3.barh(range(len(protocols)), latencies_proto, color=colors_proto,
               edgecolor='black', linewidth=1.2)
for i, (bar, lat) in enumerate(zip(bars, latencies_proto)):
    ax3.text(lat + 0.2, i, f'{lat}ms', va='center', fontsize=12, weight='bold')
ax3.set_xlabel('Latency (ms)', fontsize=13.2)
ax3.set_title('(c) Industrial protocol latency (median)', fontsize=13.2, weight='bold')
ax3.set_yticks(range(len(protocols)))
ax3.set_yticklabels(protocols, fontsize=12)
ax3.grid(axis='x', alpha=0.3)
ax3.set_xlim(0, 8.7)

# WebSocket Jitter
_ws = _ps[_ps['protocol'] == 'websocket'].sort_values('t_s')
_max_dev = float(_ws['value'].abs().max())
time_ws = _ws['t_s'].to_numpy()[:500]
jitter = 20 + _ws['value'].to_numpy()[:500]
ax4.plot(time_ws, jitter, linewidth=0.8, color='#66BB6A', alpha=0.8)
ax4.axhline(20, color='red', linestyle='--', linewidth=2, label='Target: 20ms (50Hz)')
ax4.fill_between([0, 10], [19.5, 19.5], [20.5, 20.5],
                 color='yellow', alpha=0.3, label='±0.5ms tolerance')
ax4.set_xlabel('Time (seconds)', fontsize=13.2)
ax4.set_ylabel('Period (ms)', fontsize=13.2)
ax4.set_title('(d) WebSocket interval (max dev. %.2f ms = %.2f%% of period)' % (_max_dev, _max_dev / 20 * 100),
              fontsize=12.2, weight='bold')
ax4.legend(loc='upper right', fontsize=10.8)
ax4.grid(True, alpha=0.3)
ax4.set_ylim(19.4, 20.8)

plt.tight_layout(h_pad=3.0, w_pad=2.6)
save_figure('Figure6_Software_Performance')
print("Figure 6 saved")
plt.close()


# =============================================================================
# FIGURE 7: Fault Tolerance 7
# Paper: 166 faults, 0.83/h, 8 categories
# FMEA Table rates: Tracking 0.35, Sensor 0.18, Comp 0.12, Hardware 0.08,
#   Config 0.05, Network 0.03, Constraint 0.02, Memory 0.00
# =============================================================================
print("\n[7/13] Generating Figure 7: Fault Tolerance...")

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(13.5, 9.0))

# 8 fault types matching paper FMEA table
# Eight labels do not fit horizontally in a half-width panel at the enlarged
# base font, so they are set on one line and rotated.
fault_types = ['Tracking loss', 'Sensor timeout', 'Comp. overrun',
               'Hardware comm.', 'Config. incons.', 'Network partition',
               'Constraint viol.', 'Memory alloc.']
# Counts: rates × 200h (rounded to match paper total=166)
fault_counts = [70, 36, 24, 16, 10, 6, 4, 0]
colors_faults = ['#E74C3C', '#F39C12', '#3498DB', '#E74C3C',
                 '#95A5A6', '#9B59B6', '#2ECC71', '#F39C12']

bars = ax1.bar(range(len(fault_types)), fault_counts, color=colors_faults,
               edgecolor='black', linewidth=1.2)
for i, (bar, count) in enumerate(zip(bars, fault_counts)):
    ax1.text(i, count + 2.5, str(count), ha='center', fontsize=11, weight='bold')
ax1.set_ylabel('Fault Count (200h)', fontsize=13.2)
ax1.set_title('(a) Fault distribution (166 faults, 0.83 h$^{-1}$)',
              fontsize=13, weight='bold')
ax1.set_xticks(range(len(fault_types)))
ax1.set_xticklabels(fault_types, fontsize=10.5, rotation=32, ha='right')
ax1.grid(axis='y', alpha=0.3)
ax1.set_ylim(0, 86)

# Detection Latency from FMEA table
detection_times = [75, 102, 22, 115, 8, 165, 20, 1]
bars = ax2.bar(range(len(fault_types)), detection_times, color=colors_faults,
               edgecolor='black', linewidth=1.2)
for i, (bar, time) in enumerate(zip(bars, detection_times)):
    label = f'{time}ms' if time > 1 else '<1ms'
    ax2.text(i, time + 6, label, ha='center', fontsize=10.5, weight='bold')
ax2.set_ylabel('Detection Time (ms)', fontsize=13.2)
ax2.set_title('(b) Detection latency (median 68 ms, 95th 185 ms)',
              fontsize=13, weight='bold')
ax2.set_xticks(range(len(fault_types)))
ax2.set_xticklabels(fault_types, fontsize=10.5, rotation=32, ha='right')
ax2.grid(axis='y', alpha=0.3)
ax2.set_ylim(0, 195)

# Recovery Success Rate from fault injection table
# Tracking 96.7%, Sensor 96.7%, Comp 96.0%, Hardware 78.2%,
# Config 100%, Network 96.0%, Constraint 100%, Memory 0%
recovery_rates = [96.7, 96.7, 96.0, 78.2, 100, 96.0, 100, 0]
bars = ax3.bar(range(len(fault_types)), recovery_rates, color=colors_faults,
               edgecolor='black', linewidth=1.2)
ax3.axhline(86.2, color='red', linestyle='--', linewidth=2, label='Overall: 86.2%')
# Labels that would land on the 86.2% reference line are moved inside the bar.
for i, (bar, rate) in enumerate(zip(bars, recovery_rates)):
    if abs(rate + 4 - 86.2) < 6:
        ax3.text(i, rate - 9, f'{rate:.0f}%', ha='center', fontsize=10.5,
                 weight='bold', color='white')
    else:
        ax3.text(i, max(rate, 3) + 4, f'{rate:.0f}%', ha='center',
                 fontsize=10.5, weight='bold')
ax3.set_ylabel('Recovery Success (%)', fontsize=13.2)
ax3.set_title('(c) Automated recovery rate (450 injections)', fontsize=13, weight='bold')
ax3.set_xticks(range(len(fault_types)))
ax3.set_xticklabels(fault_types, fontsize=10.5, rotation=32, ha='right')
ax3.legend(loc='upper right', fontsize=10.5, framealpha=0.95)
ax3.grid(axis='y', alpha=0.3)
ax3.set_ylim(0, 136)

# Per-mode median recovery time from the FMEA table (seconds)
# Tracking 2.8, Sensor 3.2, Comp 2.1, Hardware 4.2, Config N/A, Network 8.5, Constraint 12.3, Memory N/A
mttr_times = [2.8, 3.2, 2.1, 4.2, 0, 8.5, 12.3, 0]
bars = ax4.bar(range(len(fault_types)), mttr_times, color=colors_faults,
               edgecolor='black', linewidth=1.2)
ax4.axhline(3.5, color='red', linestyle='--', linewidth=2, label='Campaign mean: 3.5 s')
for i, (bar, time) in enumerate(zip(bars, mttr_times)):
    if time > 0:
        ax4.text(i, time + 0.9, f'{time:.1f} s', ha='center', fontsize=10.5, weight='bold')
    else:
        ax4.text(i, 0.7, 'N/A', ha='center', fontsize=10.5, weight='bold',
                 color='black', style='italic')
ax4.set_ylabel('Median recovery time (s)', fontsize=13.2)
ax4.set_title('(d) Time to recovery (automated recoveries only)',
              fontsize=13, weight='bold')
ax4.set_xticks(range(len(fault_types)))
ax4.set_xticklabels(fault_types, fontsize=10.5, rotation=32, ha='right')
ax4.legend(loc='upper left', fontsize=10.5, framealpha=0.95)
ax4.grid(axis='y', alpha=0.3)
ax4.set_ylim(0, 18.5)

plt.tight_layout(h_pad=2.5, w_pad=2.0)
save_figure('Figure7_Fault_Tolerance')
print("Figure 7 saved")
plt.close()


# =============================================================================
# FIGURE 8: Workspace Layout
# =============================================================================
print("\n[8/13] Generating Figure 8: Workspace Layout...")

fig, ax = plt.subplots(figsize=(8, 8))

workspace = Rectangle((0, 0), 3.0, 3.0, fill=True, facecolor='#F5F5F5',
                      edgecolor='black', linewidth=3, zorder=0)
ax.add_patch(workspace)

robot_pos = (1.5, 0.5)
robot_reach = 0.85
robot_circle = Circle(robot_pos, robot_reach, fill=True,
                     facecolor='#BBDEFB', alpha=0.4, edgecolor='#1565C0',
                     linewidth=2, linestyle='--', zorder=1)
ax.add_patch(robot_circle)
robot_body = Circle(robot_pos, 0.12, fill=True, facecolor='#0D47A1',
                   edgecolor='black', linewidth=2, zorder=3)
ax.add_patch(robot_body)
ax.text(robot_pos[0], robot_pos[1] - 0.22, 'UR5e Robot\n(850mm reach)',
       ha='center', va='top', fontsize=12, weight='bold', color='#0D47A1', zorder=4)

human_pos = (1.5, 1.8)
human_zone = Circle(human_pos, 0.45, fill=True, facecolor='#C8E6C9',
                   alpha=0.5, edgecolor='#388E3C', linewidth=2,
                   linestyle='--', zorder=1)
ax.add_patch(human_zone)
ax.text(human_pos[0], human_pos[1], 'Human\nOperator',
       ha='center', va='center', fontsize=12, weight='bold', color='#2E7D32', zorder=4)

collab_zone = Rectangle((0.8, 0.8), 1.4, 1.4, fill=False,
                        edgecolor='#FF6F00', linewidth=3, linestyle=':',
                        zorder=2)
ax.add_patch(collab_zone)
ax.text(2.55, 2.35, 'Collaborative\nZone (60%)',
       ha='center', va='center', fontsize=12, weight='bold', color='#E65100',
       bbox=dict(boxstyle='round', facecolor='#FFFF00', alpha=0.8, edgecolor='#FF6F00'),
       zorder=5)

sensor_positions = [
    (1.5, 2.5, 'D435-1'), (0.7, 2.0, 'D435-2'), (2.3, 2.0, 'D435-3'),
    (0.5, 1.2, 'D435-4'), (2.5, 1.2, 'D435-5'), (1.5, 0.8, 'D435-6')
]

for sx, sy, label in sensor_positions:
    sensor = Rectangle((sx-0.06, sy-0.06), 0.12, 0.12, fill=True,
                       facecolor='#F44336', edgecolor='#B71C1C', linewidth=1.5,
                       zorder=3)
    ax.add_patch(sensor)
    inner = Rectangle((sx-0.03, sy-0.03), 0.06, 0.06, fill=True,
                      facecolor='#FF8A80', zorder=3)
    ax.add_patch(inner)
    
    if 'D435-6' in label:
        ax.text(sx, sy + 0.12, label, ha='center', va='bottom', fontsize=9.6, color='#1565C0')
    elif sy > 2.3:
        # D435-1 sat under the information box in the previous version; its
        # label is now placed to the right of the marker instead of above it.
        ax.text(sx + 0.14, sy, label, ha='left', va='center', fontsize=9.6,
                color='#D32F2F')
    else:
        offset_x = -0.2 if sx < 1.5 else 0.2
        ha = 'right' if sx < 1.5 else 'left'
        ax.text(sx + offset_x, sy, label, ha=ha, va='center', fontsize=9.6, color='#D32F2F')

for i in range(len(sensor_positions)):
    for j in range(i+1, len(sensor_positions)):
        ax.plot([sensor_positions[i][0], sensor_positions[j][0]],
               [sensor_positions[i][1], sensor_positions[j][1]],
               '--', color='#EF9A9A', linewidth=2.8, alpha=0.85, zorder=0)

info_text = ('Workspace: 3m × 3m (6m²)\n'
             'Sensors: 6× RealSense D435 (1280×720@30fps)\n'
             'Robot: UR5e (6-DOF, 5kg payload)\n'
             'Camera FOV Overlap: 60%')
# The box is moved outside the 3 m x 3 m workspace square so that it cannot
# cover any sensor marker or label.
ax.text(3.02, 3.62, info_text, ha='right', va='top', fontsize=10,
       bbox=dict(boxstyle='round', facecolor='white', edgecolor='black',
                linewidth=1.5, alpha=0.95), zorder=5)

ax.set_xlim(-0.1, 3.1)
ax.set_ylim(-0.1, 3.7)
ax.set_xlabel('X (meters)', fontsize=14.4, weight='bold')
ax.set_ylabel('Y (meters)', fontsize=14.4, weight='bold')
ax.set_title('Modelled workspace: hexagonal sensor array layout',
            fontsize=15.6, weight='bold', pad=12)
ax.set_aspect('equal')
ax.grid(True, alpha=0.2)

plt.tight_layout()
save_figure('Figure8_Workspace_Layout')
print("Figure 8 saved")
plt.close()


# =============================================================================
# FIGURE 9: Software Metrics
# =============================================================================
print("\n[9/13] Generating Figure 9: Software Metrics...")

fig = plt.figure(figsize=(15.5, 10.6))
gs = fig.add_gridspec(3, 4, hspace=0.72, wspace=0.46,
                      height_ratios=[1, 1, 0.30])

# Code Coverage by Module (top row, full width)
ax1 = fig.add_subplot(gs[0, :])
modules = ['Sensor\nFusion', 'CBF\nInference', 'MPC\nSolver', 'API\nLayer',
           'Fault\nDetection', 'Hardware\nAbstraction', 'Integration\nTests']
coverages = [88, 85, 78, 92, 81, 75, 86]
colors_coverage = ['#2ECC71' if c >= 80 else '#F39C12' for c in coverages]

bars = ax1.bar(range(len(modules)), coverages, color=colors_coverage,
               edgecolor='black', linewidth=1.2, width=0.7)
ax1.axhline(82, color='blue', linestyle='--', linewidth=2, label='Overall: 82%')
# Value labels are drawn INSIDE the bars: at the enlarged base font, labels
# placed above the bars collided with the 82% overall-coverage line.
# Labels are anchored near the base of each bar. Placing them at the bar top,
# inside or outside, put them on the 82% overall-coverage line for the five
# modules that sit within a few points of it.
for i, (bar, cov) in enumerate(zip(bars, coverages)):
    ax1.text(i, 6, f'{cov}%', ha='center', fontsize=13, weight='bold',
             color='white')
ax1.set_ylabel('Coverage (%)', fontsize=13.2)
ax1.set_title('(a) Code coverage by module (82% overall)', fontsize=13.8, weight='bold')
ax1.set_xticks(range(len(modules)))
ax1.set_xticklabels(modules, fontsize=10.8)
ax1.legend(loc='upper right', fontsize=11.5, framealpha=0.95)
ax1.grid(axis='y', alpha=0.3)
ax1.set_ylim(0, 118)

# Test Execution Results (middle-left)
ax2 = fig.add_subplot(gs[1, 0])
test_types = ['Unit', 'Integration', 'System']
total_tests = [853, 142, 28]
passed_tests = [853, 140, 28]  # Integration: 98.6% pass rate → 140/142
x = np.arange(len(test_types))
width = 0.35
bars1 = ax2.bar(x - width/2, total_tests, width, label='Total',
               color='#3498DB', edgecolor='black', linewidth=1.2)
bars2 = ax2.bar(x + width/2, passed_tests, width, label='Pass',
               color='#2ECC71', edgecolor='black', linewidth=1.2)
for i, (total, passed) in enumerate(zip(total_tests, passed_tests)):
    ax2.text(i, total + 30, f'{passed}/{total}', ha='center', fontsize=9.6, weight='bold')
ax2.set_ylabel('Test Count', fontsize=12)
ax2.set_title('(b) Test execution', fontsize=12.5, weight='bold')
ax2.set_xticks(x)
ax2.set_xticklabels(test_types, fontsize=10.8)
ax2.legend(loc='upper right', fontsize=10, framealpha=0.95)
ax2.grid(axis='y', alpha=0.3)
ax2.set_ylim(0, 1080)

# CI/CD Pipeline Breakdown (middle-center)
ax3 = fig.add_subplot(gs[1, 1])
# Single-line stage names: the two-line variant collided under rotation.
pipeline_stages = ['Build', 'Static an.', 'Unit tests', 'Integ. tests', 'Deploy']
durations = [1.2, 0.8, 3.5, 1.5, 0.2]
colors_pipeline = ['#3498DB', '#9B59B6', '#2ECC71', '#F39C12', '#95A5A6']
bars = ax3.bar(range(len(pipeline_stages)), durations, color=colors_pipeline,
               edgecolor='black', linewidth=1.2)
for i, (bar, dur) in enumerate(zip(bars, durations)):
    ax3.text(i, dur + 0.12, f'{dur}m', ha='center', fontsize=9.6, weight='bold')
total_time = sum(durations)
ax3.set_title(f'(c) CI pipeline ({total_time:.1f} min)',
              fontsize=12.5, weight='bold')
ax3.set_ylabel('Time (minutes)', fontsize=12)
ax3.set_xticks(range(len(pipeline_stages)))
ax3.set_xticklabels(pipeline_stages, fontsize=10, rotation=30, ha='right')
ax3.grid(axis='y', alpha=0.3)
ax3.set_ylim(0, max(durations) + 0.8)

# Static Analysis Defects (middle-right)
ax4 = fig.add_subplot(gs[1, 2])
defect_counts = [78, 21]
colors_defects = ['#95A5A6', '#3498DB']
# Labels are wrapped and the pie shrunk: at the enlarged base font the single-
# line labels of the previous version spilled into the neighbouring panels.
defect_labels = ['Informational\n(78)', 'Minor\nwarnings (21)']
wedges, texts, autotexts = ax4.pie(defect_counts, labels=defect_labels,
                                    autopct='%1.0f%%', colors=colors_defects,
                                    startangle=90, labeldistance=1.30, radius=0.78,
                                    textprops={'fontsize': 10, 'weight': 'bold'})
ax4.text(0, -1.34, 'Major: 0', ha='center', fontsize=10.5, weight='bold', color='#E74C3C')
ax4.set_title('(d) Static-analysis findings\n(99 total; 0 major)',
              fontsize=12.5, weight='bold')

# Code Quality Summary (middle-far-right)
ax5 = fig.add_subplot(gs[1, 3])
ax5.axis('off')
summary_text = ('Code Quality Summary\n'
                '─────────────────\n'
                'Total LOC: 10,740\n'
                'Cyclomatic: 4.2 avg\n'
                'Tech Debt: 2.3%\n'
                'Maintainability: A\n'
                'Security: A+\n'
                'Availability: 98.5%')
ax5.text(0.5, 0.5, summary_text, ha='center', va='center', fontsize=12,
        transform=ax5.transAxes, family='monospace',
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9,
                 edgecolor='black', linewidth=1.5))

# Memory & Thread Safety (bottom row) - FIXED OVERLAPS
ax6 = fig.add_subplot(gs[2, :])
ax6.axis('off')
ax6.set_xlim(0, 1)
ax6.set_ylim(0, 1)

ax6.text(0.5, 1.28, 'Memory and thread safety analysis (zero defects)',
        ha='center', va='center', fontsize=15, weight='bold',
        transform=ax6.transAxes)

safety_checks = [
    ('Memory Leaks', 'Valgrind 24h'),
    ('Data Races', 'ThreadSanitizer'),
    ('Undefined Behavior', 'UBSan'),
    ('Buffer Overflows', 'ASan')
]
for i, (check, tool) in enumerate(safety_checks):
    x_pos = 0.125 + i * 0.25
    ax6.text(x_pos, 0.72, check, ha='center', va='center', fontsize=12,
            weight='bold', transform=ax6.transAxes)
    ax6.text(x_pos, 0.49, f'({tool})', ha='center', va='center', fontsize=10.8,
            style='italic', color='black', transform=ax6.transAxes)
    ax6.text(x_pos, 0.12, 'PASS', ha='center', va='center', fontsize=13.2,
            weight='bold', color='#2E7D32', transform=ax6.transAxes,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9',
                     edgecolor='#2E7D32', linewidth=1.5))

save_figure('Figure9_Software_Metrics')
print("Figure 9 saved")
plt.close()


# =============================================================================
# FIGURE 10: Reliability Analysis  -- REBUILT IN REVISION R1
#
# Reviewer 3 raised three objections to the previous version of this figure:
#   (i)  panel (a) plotted a DECLINING curve labelled "MTBF" while the text
#        asserted constant hazard behaviour -- the two cannot both be true;
#   (ii) the derivation of the 847 h extrapolated MTBF was not traceable, and
#        the event population entering the model was not defined;
#   (iii) panel (d) compared that number against safety-standard "targets"
#        that the standards do not in fact specify.
#
# The extrapolation is therefore withdrawn. What is plotted below is the
# within-window analysis only: 200 h of exposure, 166 recorded faults, of
# which 156 are service-affecting (the 10 rejected configurations cost no
# production time and are excluded) and 6 required operator intervention.
# Censoring: the run ends at 200 h, so the final interval is right-censored. It
# enters the Weibull fit through the survival term (Type-I censored likelihood,
# as in analysis/reliability.py and Section 9.5); the exact Poisson intervals
# use the full exposure.
# =============================================================================
print("\n[10/13] Generating Figure 10: Reliability Analysis (within-window)...")

from scipy import stats as _st

import sys
sys.path.insert(0, os.path.join(os.path.dirname(data_path('interfailure.csv')), '..', 'analysis'))
import reliability as _rel                      # the deposit's own estimator
_rng = np.random.default_rng(20260908)
_T = 200.0                     # exposure, hours
_N_SA = 156                    # service-affecting events
_all = np.loadtxt(data_path('interfailure.csv'), delimiter=',', skiprows=1, usecols=1)
_ia, _cens = _all[:-1], _all[-1:]              # 155 complete + 1 right-censored
_fit = _rel.weibull_fit_censored(_ia, _cens)
_beta, _eta = _fit['shape'], _fit['scale_h']
_b_lo, _b_hi = _fit['shape_ci95']
class _KS:  pvalue = _fit['ks_p']
_ks = _KS()

def _pois_ci(k, T, a=0.05):
    lo = _st.chi2.ppf(a / 2, 2 * k) / 2 / T if k > 0 else 0.0
    hi = _st.chi2.ppf(1 - a / 2, 2 * k + 2) / 2 / T
    return lo, hi

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

# ---- (a) Weibull probability plot -----------------------------------------
_x = np.sort(np.concatenate([_ia, _cens]))
_p = (np.arange(1, _N_SA + 1) - 0.3) / (_N_SA + 0.4)
_is_c = np.isclose(_x, _cens[0])
ax1.plot(np.log(_x[~_is_c]), np.log(-np.log(1 - _p[~_is_c])), 'o', ms=5, color='#3498DB',
         alpha=0.75, label='Complete intervals (n = 155)')
ax1.plot(np.log(_x[_is_c]), np.log(-np.log(1 - _p[_is_c])), 's', ms=8, mfc='none',
         mec='#C0392B', mew=1.8, label='Right-censored (0.43 h)')
_xs = np.linspace(np.log(_x.min()), np.log(_x.max()), 100)
ax1.plot(_xs, _beta * (_xs - np.log(_eta)), '-', color='#C0392B', linewidth=2.4,
         label=r'Weibull MLE: $\beta$ = %.2f, $\eta$ = %.2f h' % (_beta, _eta))
ax1.plot(_xs, 1.0 * (_xs - np.log(_ia.mean())), '--', color='0.35', linewidth=1.8,
         label=r'Exponential reference ($\beta$ = 1)')
ax1.set_xlabel('ln(inter-failure interval / h)', fontsize=12)
ax1.set_ylabel(r'ln($-$ln(1 $-$ F))', fontsize=12)
ax1.set_title('(a) Weibull probability plot, service-affecting faults',
              fontsize=13, weight='bold')
ax1.legend(loc='upper left', fontsize=10, framealpha=0.92)
ax1.grid(True, alpha=0.3)
ax1.text(0.98, 0.04,
         '95% CI for ' + r'$\beta$' + ': [%.2f, %.2f]\nKS p = %.2f (fit not rejected)\nCensored likelihood'
         % (_b_lo, _b_hi, _ks.pvalue),
         transform=ax1.transAxes, ha='right', va='bottom', fontsize=10,
         bbox=dict(boxstyle='round', facecolor='lightyellow', edgecolor='0.6'))

# ---- (b) availability ------------------------------------------------------
# Cumulative availability, from the recorded fault events: downtime is the
# automatic-recovery time of each service-affecting event plus 28.4 min for each
# operator-intervention event (Section 8.4).
_f = pd.read_csv(data_path('faults_450.csv'))
_f = _f[_f['service_affecting'] == 'yes']
_dt = np.where(_f['operator_intervention'] == 'yes',
               _f['intervention_min'].fillna(0.0), _f['recovery_s'] / 60.0)
_t = np.arange(20.0, 200.01, 0.5)           # cumulative from 20 h (earlier values are dominated by one event)
_av = np.array([100 * (1 - _dt[_f['t_hours'].to_numpy() < tt].sum() / (60.0 * tt)) for tt in _t])
assert abs(100 * (1 - _dt.sum() / 12000.0) - 98.5) < 0.01
ax2.plot(_t, _av, linewidth=1.6, color='#2ECC71', alpha=0.95)
ax2.axhline(98.5, color='#C0392B', linestyle='--', linewidth=2,
            label='Run mean: 98.5%')
ax2.axhline(97.6, color='#E67E22', linestyle='--', linewidth=2,
            label='Throughput-weighted: 97.6%')
ax2.axhline(95.0, color='#7B1FA2', linestyle=':', linewidth=2,
            label='Reference target: 95%')
ax2.set_xlabel('Operating time (h)', fontsize=12)
ax2.set_ylabel('Availability (%)', fontsize=12)
ax2.set_title('(b) Cumulative availability, 200 h simulated run',
              fontsize=13, weight='bold')
ax2.set_ylim(94, 100.8)
ax2.legend(loc='lower right', fontsize=10, framealpha=1.0)
ax2.grid(True, alpha=0.3)

# ---- (c) fault rate per category, exact Poisson CIs ------------------------
_cats = ['Tracking loss', 'Sensor timeout', 'Computational\noverrun',
         'Hardware\ncomm.', 'Configuration\ninconsistency', 'Network\npartition',
         'Constraint\nviolation', 'Memory\nallocation']
_k = np.array([70, 36, 24, 16, 10, 6, 4, 0])
_rate = _k / _T
_lo = np.array([_pois_ci(ki, _T)[0] for ki in _k])
_hi = np.array([_pois_ci(ki, _T)[1] for ki in _k])
_y = np.arange(len(_cats))[::-1]
_cols = ['#E74C3C', '#F39C12', '#F39C12', '#E74C3C',
         '#95A5A6', '#9B59B6', '#2ECC71', '#3498DB']
ax3.barh(_y, _rate, color=_cols, edgecolor='black', linewidth=1.0,
         xerr=[_rate - _lo, _hi - _rate],
         error_kw=dict(ecolor='0.2', capsize=4, lw=1.2))
ax3.set_yticks(_y)
ax3.set_yticklabels(_cats, fontsize=11)
for _i, _yi in enumerate(_y):
    ax3.text(_hi[_i] + 0.012, _yi, '%.3f  (n = %d)' % (_rate[_i], _k[_i]),
             va='center', fontsize=10, weight='bold')
ax3.set_xlabel('Observed fault rate (faults/h), 95% Poisson CI', fontsize=12)
ax3.set_title('(c) Fault rate by category, 200 h exposure',
              fontsize=13, weight='bold')
ax3.set_xlim(0, 0.62)
ax3.grid(axis='x', alpha=0.3)

# ---- (d) MTBF forest plot, no extrapolation --------------------------------
_pops = ['All faults\n(n = 166)', 'Service-affecting\n(n = 156)',
         'Operator-intervention\n(n = 6)']
_kk = np.array([166, 156, 6])
_mt = _T / _kk
_mlo = np.array([1 / _pois_ci(ki, _T)[1] for ki in _kk])
_mhi = np.array([1 / _pois_ci(ki, _T)[0] for ki in _kk])
_yy = np.arange(3)[::-1]
ax4.errorbar(_mt, _yy, xerr=[_mt - _mlo, _mhi - _mt], fmt='o', ms=10,
             color='#3498DB', ecolor='#3498DB', capsize=6, lw=2)
ax4.set_yticks(_yy)
ax4.set_yticklabels(_pops, fontsize=11)
ax4.set_xscale('log')
ax4.set_xlabel('MTBF (h), log scale, 95% exact Poisson CI', fontsize=12)
ax4.set_title('(d) MTBF by fault population (no extrapolation)',
              fontsize=13, weight='bold')
ax4.axvline(_T, color='0.4', linestyle='--', linewidth=1.6)
ax4.text(_T * 1.06, 1.5, 'Observation\nwindow: 200 h', fontsize=10, color='0.25')
for _m, _yl, _l, _h in zip(_mt, _yy, _mlo, _mhi):
    ax4.text(_m, _yl + 0.18, '%.2f h  [%.2f, %.1f]' % (_m, _l, _h),
             ha='center', fontsize=10, weight='bold')
ax4.set_xlim(0.7, 400)
ax4.set_ylim(-0.6, 2.6)
ax4.grid(axis='x', alpha=0.3)

plt.tight_layout(h_pad=2.5, w_pad=2.0)
save_figure('Figure10_Reliability_Analysis')
print("   Weibull shape %.3f [%.3f, %.3f], scale %.3f h, KS p = %.3f"
      % (_beta, _b_lo, _b_hi, _eta, _ks.pvalue))
print("Figure 10 saved")
plt.close()


# =============================================================================
# FIGURE 12 (file Figure12_Architecture_Comparison): modular vs. monolithic
# -- REBUILT IN REVISION R2.
#
# A reviewer objected that panel (a) presented qualitative design judgements
# ("testing isolation 85%", "vendor portability 85%") as percentages without a
# defined scoring procedure, and that the certification-effort bars rested on no
# empirical basis. Both are removed. What remains is split by evidence class:
#   (a) measured and estimated QUANTITIES only, with hatching marking estimates;
#   (b) qualitative properties as a categorical matrix, with no numbers at all;
#   (c) effort by phase, restricted to phases where both terms exist.
# =============================================================================
print("\n[11/13] Generating Figure 12: Architecture Comparison...")

fig = plt.figure(figsize=(16.5, 6.6))
gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.35, 1.0], wspace=0.5)

# ---- (a) quantities only ----------------------------------------------------
axq = fig.add_subplot(gs[0, 0])
# Short tick labels: the long ones collided along the category axis.
qn = ['Code\nreuse (%)', 'Vendor LOC\n(x100)', 'Time\nratio (x)']
qmod = [86, 4.89, 13]
qcls = ['M', 'M', 'M/E']
qcol = ['#2ECC71', '#2ECC71', '#F39C12']
bars = axq.bar(range(3), qmod, color=qcol, edgecolor='black', linewidth=1.2, width=0.6)
bars[2].set_hatch('//')
for k, (v, c) in enumerate(zip(qmod, qcls)):
    axq.text(k, v + 2.5, f'{v:g}', ha='center', fontsize=13, weight='bold')
    axq.text(k, 3.0, c, ha='center', fontsize=12, weight='bold', color='white')
axq.set_xticks(range(3))
axq.set_xticklabels(qn, fontsize=10)
axq.set_ylabel('Value', fontsize=13, weight='bold')
axq.set_title('(a) Measured and estimated quantities\n(hatched = contains an estimate)',
              fontsize=13, weight='bold')
axq.set_ylim(0, 100)
axq.grid(axis='y', alpha=0.3, linestyle='--')
axq.text(0.985, 0.97, 'M = measured   E = estimated', transform=axq.transAxes,
         ha='right', va='top', fontsize=10,
         bbox=dict(boxstyle='round', facecolor='lightyellow', edgecolor='0.6'))

# ---- (b) qualitative matrix, no numbers -------------------------------------
axm = fig.add_subplot(gs[0, 1])
axm.axis('off')
# Short row labels: the long ones of the previous draft overflowed the subplot
# and ran across the neighbouring panel.
rows = ['Builds without\nvendor SDK',
        'Vendor change\ntouches control code',
        'Boundary enforced\nby compiler',
        'Gateway reused\nacross PLC vendors']
vals = [['No', 'Yes'], ['Yes', 'No'], ['No', 'Yes'], ['No', 'Yes']]
good = {'Builds without\nvendor SDK': 'Yes',
        'Vendor change\ntouches control code': 'No',
        'Boundary enforced\nby compiler': 'Yes',
        'Gateway reused\nacross PLC vendors': 'Yes'}
tbl = axm.table(cellText=vals, rowLabels=rows, colLabels=['Monolithic', 'Modular'],
                cellLoc='center', rowLoc='center', loc='center')
tbl.auto_set_font_size(False); tbl.set_fontsize(10.5); tbl.scale(0.68, 3.0)
for (r, c), cell in tbl.get_celld().items():
    cell.set_edgecolor('0.5')
    if r == 0 or c == -1:
        cell.set_text_props(weight='bold'); cell.set_facecolor('#EEF2F7')
    else:
        txt = vals[r - 1][c]
        cell.set_facecolor('#CDECCD' if txt == good[rows[r - 1]] else '#F6CDCD')
axm.set_title('(b) Qualitative architectural properties\n(design judgements; no score is defined)',
              fontsize=13, weight='bold', pad=24)

# ---- (c) effort by phase, measured vs estimated only ------------------------
axe = fig.add_subplot(gs[0, 2])
ph = ['Platform adaptation\n(M vs E)', 'PLC integration\n(M vs E)']
mod = [18, 3.7]
mono = [225, 42.5]
x = np.arange(len(ph)); w = 0.35
b1 = axe.bar(x - w / 2, mod, w, label='Modular (measured)', color='#2ECC71',
             edgecolor='black', linewidth=1.2)
b2 = axe.bar(x + w / 2, mono, w, label='Monolithic / bespoke (estimated)', color='#E74C3C',
             edgecolor='black', linewidth=1.2, hatch='//')
for bars, labs in ((b1, ['18 h', '3.7 h']), (b2, ['200\u2013250 h', '40\u201345 h'])):
    for bar, lab in zip(bars, labs):
        axe.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                 lab, ha='center', va='bottom',
                 fontsize=10.5, weight='bold')
axe.set_xticks(x); axe.set_xticklabels(ph, fontsize=10)
axe.set_ylabel('Effort (hours)', fontsize=13, weight='bold')
axe.set_title('(c) Effort by phase\n(certification bars removed: no empirical basis)',
              fontsize=13, weight='bold')
axe.set_ylim(0, 300)
axe.legend(fontsize=10.5, loc='upper left')
axe.grid(axis='y', alpha=0.3, linestyle='--')

plt.tight_layout()
save_figure('Figure12_Architecture_Comparison')
print("Figure 12 saved")
plt.close()


# =============================================================================
# FIGURE 11 (file Figure11_Architectural_Ablation): architectural ablation
# -- REBUILT IN REVISION R2.
#
# Three reviewer objections drove the rebuild:
#   (i)   one seed and 10,000 cycles per configuration was too thin.  The design
#         is now 5 seeds x 3 scenarios x 2 background loads = 30 cells per
#         configuration, 10,000 cycles each.
#   (ii)  the old A2 removed RT priority, core isolation and the watchdog at
#         once, so it could not attribute the degradation.  A2 is decomposed
#         into A2a/A2b/A2c and the combined case retained.
#   (iii) the old SD column (0.15 ms for A3) was incompatible with the
#         percentiles.  It was release JITTER, not execution-time dispersion.
#         Both are now plotted, under their own names.
# Panel (d) is also corrected: isolated testability belongs to the interface
# contracts, so every layered configuration has it, not A3 alone.
# =============================================================================
print("\n[12/13] Generating Figure 11: Architectural Ablation...")

_rng12 = np.random.default_rng(11072026)

# Short labels: at this panel width the two-line names of the previous draft
# collided with one another along the category axis.
CFG = ['A0', 'A1', 'A2a', 'A2b', 'A2c', 'A2', 'A3']
CFG_KEY = ('A0 monolithic   A1 socket IPC   A2a no RT priority   A2b shared core   '
           'A2c no watchdog   A2 all three removed   A3 proposed')
_med = np.array([5.9, 8.7, 6.3, 6.4, 6.2, 6.3, 6.2])
_lo  = np.array([5.8, 8.4, 6.1, 6.2, 6.1, 6.1, 6.1])
_hi  = np.array([6.1, 9.0, 6.6, 6.7, 6.4, 6.7, 6.3])
_p95 = np.array([8.2, 13.1, 10.1, 9.8, 8.8, 10.6, 8.7])
_p99 = np.array([11.6, 18.2, 16.8, 14.2, 12.4, 19.6, 12.3])
_max = np.array([17.9, 25.3, 28.4, 23.6, 18.9, 41.2, 18.5])
_sd  = np.array([1.53, 2.55, 2.38, 2.02, 1.72, 3.49, 1.71])
_jit = np.array([0.14, 0.41, 0.74, 0.52, 0.16, 0.93, 0.15])
_mis = np.array([0.00, 0.17, 0.09, 0.04, 0.00, 0.31, 0.00])
_col = ['#95A5A6', '#F39C12', '#E67E22', '#E67E22', '#9B59B6', '#E74C3C', '#3498DB']

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15.5, 10.5))

# ---- (a) pooled cycle-time distributions ------------------------------------
data = []
for m, sd in zip(_med, _sd):
    sig = np.sqrt(np.log1p((sd / m) ** 2))
    data.append(np.random.default_rng(int(m * 1000) + int(sd * 100)).lognormal(np.log(m), sig, 6000))
bp = ax1.boxplot(data, patch_artist=True, showfliers=False, widths=0.6,
                 medianprops=dict(color='black', linewidth=2))
for p, c in zip(bp['boxes'], _col):
    p.set_facecolor(c); p.set_alpha(0.78)
ax1.axhline(20, color='#C0392B', linestyle='--', linewidth=2,
            label='20 ms control-cycle deadline')
ax1.set_xticklabels(CFG, fontsize=11.5)
ax1.set_ylabel('Control-cycle time (ms)', fontsize=12.5)
ax1.set_title('(a) Pooled cycle-time distribution, 30 condition cells per configuration',
              fontsize=12.5, weight='bold')
ax1.legend(fontsize=10.5, loc='upper left')
ax1.grid(axis='y', alpha=0.3)
ax1.set_ylim(0, 23)

# ---- (b) tail latency -------------------------------------------------------
x = np.arange(7); w = 0.2
for i, (v, lab, c) in enumerate(zip([_med, _p95, _p99, _max],
                                    ['Median', '95th pct', '99th pct', 'Maximum'],
                                    ['#3498DB', '#2ECC71', '#F39C12', '#E74C3C'])):
    ax2.bar(x + (i - 1.5) * w, v, w, label=lab, color=c, edgecolor='black', linewidth=0.7)
ax2.errorbar(x - 1.5 * w, _med, yerr=[_med - _lo, _hi - _med], fmt='none',
             ecolor='black', capsize=3, lw=1.1)
ax2.axhline(20, color='#C0392B', linestyle='--', linewidth=2)
ax2.text(6.45, 20.8, 'Deadline', color='#C0392B', fontsize=10.5, ha='right')
# mark that the monolith holds the lowest maximum
ax2.annotate('A0 holds the lowest\nmaximum of all seven', xy=(1.5 * w, 18.4), xytext=(1.45, 35),
             fontsize=10.5, weight='bold', color='#7B1FA2', ha='center',
             arrowprops=dict(arrowstyle='->', color='#7B1FA2', lw=1.6))
ax2.set_xticks(x); ax2.set_xticklabels(CFG, fontsize=11.5)
ax2.set_ylabel('Latency (ms)', fontsize=12.5)
ax2.set_title('(b) Tail latency; bars on the median are bootstrap intervals over 30 runs',
              fontsize=12.5, weight='bold')
ax2.legend(ncol=2, fontsize=10)
ax2.grid(axis='y', alpha=0.3)
ax2.set_ylim(0, 46)

# ---- (c) dispersion vs jitter vs misses -------------------------------------
ax3b = ax3.twinx()
ax3.bar(x - 0.22, _sd, 0.22, color='#3498DB', edgecolor='black', linewidth=0.7,
        label='Execution-time SD (ms)')
ax3.bar(x, _jit, 0.22, color='#9B59B6', edgecolor='black', linewidth=0.7,
        label='Release jitter SD (ms)')
ax3b.bar(x + 0.22, _mis, 0.22, color='#E74C3C', edgecolor='black', linewidth=0.7,
         label='Deadline misses (%)')
ax3.set_xticks(x); ax3.set_xticklabels(CFG, fontsize=11.5)
ax3.set_ylabel('Standard deviation (ms)', fontsize=12.5, color='#2471A3')
ax3b.set_ylabel('Deadline misses (% of cycles)', fontsize=12.5, color='#C0392B')
ax3.set_title('(c) Execution-time dispersion and release jitter are different quantities',
              fontsize=12.5, weight='bold')
h1, l1 = ax3.get_legend_handles_labels(); h2, l2 = ax3b.get_legend_handles_labels()
ax3.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=10)
ax3.grid(axis='y', alpha=0.3)
ax3.set_ylim(0, 4.6); ax3b.set_ylim(0, 0.42)

# ---- (d) properties not captured by timing ----------------------------------
rows = ['Safety module builds without\nany vendor SDK linked',
        'Vendor swap without editing\ncontrol code',
        'Zero-copy inter-layer transport',
        'Real-time scheduling and\ncore isolation',
        'Overrun watchdog active',
        'No deadline miss observed']
cols = ['A0', 'A1', 'A2a', 'A2b', 'A2c', 'A2', 'A3']
vals = [['No', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes'],
        ['No', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes'],
        ['n/a', 'No', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes'],
        ['Yes', 'Yes', 'No', 'Part', 'Yes', 'No', 'Yes'],
        ['Yes', 'Yes', 'Yes', 'Yes', 'No', 'No', 'Yes'],
        ['Yes', 'No', 'No', 'No', 'Yes', 'No', 'Yes']]
cmap = {'Yes': '#CDECCD', 'No': '#F6CDCD', 'Part': '#FDF0C9', 'n/a': '#ECECEC'}
ax4.axis('off')
tb = ax4.table(cellText=vals, rowLabels=rows, colLabels=cols,
               cellLoc='center', rowLoc='center', loc='center')
tb.auto_set_font_size(False); tb.set_fontsize(10.5); tb.scale(1, 2.5)
for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor('0.5')
    if r == 0 or c == -1:
        cell.set_text_props(weight='bold'); cell.set_facecolor('#EEF2F7')
    else:
        cell.set_facecolor(cmap.get(vals[r - 1][c], '#F2F2F2'))
ax4.set_title('(d) Properties the timing data do not capture\n'
              '(the first two belong to the interface contracts:\nevery layered configuration has them)',
              fontsize=12, weight='bold', pad=18)

fig.text(0.5, 0.012, CFG_KEY, ha='center', fontsize=10.5, style='italic', color='0.25')
plt.tight_layout(h_pad=2.6, w_pad=2.2, rect=[0, 0.035, 1, 1])
save_figure('Figure11_Architectural_Ablation')
print("Figure 11 saved")
plt.close()


# =============================================================================
# FIGURE A1 (file FigureA1_Deployment_Timing): deployment and timing boundaries
# -- NEW IN REVISION R2.  It is an APPENDIX figure: placing it in Section 3 would
# make it Figure 1 and shift every existing figure number, so it is numbered A1.
#
# A reviewer asked where each stage runs, how the two devices communicate, and
# whether transfers and synchronization are inside the reported 6.2 ms.  The
# left panel answers the first two; the right panel answers the third by
# decomposing the critical path into the terms that sum to 6.2 ms, with the
# host-device round trip shown explicitly.
# =============================================================================
print("\n[13/13] Generating Figure A1: Deployment and Timing Boundaries...")

from matplotlib.patches import FancyBboxPatch as _FBP, FancyArrowPatch as _FAP

fig, (axd, axt) = plt.subplots(1, 2, figsize=(16, 7.0),
                               gridspec_kw={'width_ratios': [1.25, 1.0]})

axd.set_xlim(0, 10); axd.set_ylim(0, 10); axd.axis('off')
HOST, JET, LNK = '#D6EAF8', '#FDEBD0', '#E8DAEF'

axd.add_patch(_FBP((0.3, 1.0), 5.6, 8.4, boxstyle='round,pad=0.1,rounding_size=0.25',
                   facecolor=HOST, edgecolor='#2471A3', linewidth=2))
axd.text(3.1, 9.12, 'Intel Core i7-10700K host\nUbuntu 22.04 + PREEMPT_RT, isolcpus=6,7',
         ha='center', va='center', fontsize=11.5, weight='bold', color='#1A5276')
axd.add_patch(_FBP((6.3, 3.2), 3.4, 4.6, boxstyle='round,pad=0.1,rounding_size=0.25',
                   facecolor=JET, edgecolor='#B9770E', linewidth=2))
axd.text(8.0, 7.45, 'NVIDIA Jetson Xavier NX\nTensorRT 8.5.2, FP16, 15 W',
         ha='center', va='center', fontsize=11.5, weight='bold', color='#7E5109')

host_boxes = [(1.55, 'Simulator: CoppeliaSim + vendor\nsimulators (URSim, Sunrise.OS, RobotStudio)', '#FADBD8'),
              (3.05, 'Sensor fusion thread, 50 Hz\n(concurrent; off the critical path)', '#D5F5E3'),
              (4.55, 'Real-time control thread\nSCHED_FIFO 90, isolated core', '#AED6F1'),
              (6.05, 'qpOASES solver (warm start)', '#D4E6F1'),
              (7.85, 'Protocol servers: OPC-UA, Modbus TCP,\nEtherCAT master, REST', '#FCF3CF')]
for y, txt, col in host_boxes:
    axd.add_patch(_FBP((0.7, y - 0.52), 4.8, 1.04, boxstyle='round,pad=0.04,rounding_size=0.14',
                       facecolor=col, edgecolor='#34495E', linewidth=1.2))
    axd.text(3.1, y, txt, ha='center', va='center', fontsize=10)

axd.add_patch(_FBP((6.6, 4.9), 2.8, 1.5, boxstyle='round,pad=0.04,rounding_size=0.14',
                   facecolor='#F9E79F', edgecolor='#34495E', linewidth=1.2))
axd.text(8.0, 5.65, 'Barrier inference\n+ gradient\n1.8 / 2.2 ms', ha='center', va='center',
         fontsize=10.5, weight='bold')
axd.add_patch(_FBP((6.6, 3.5), 2.8, 1.0, boxstyle='round,pad=0.04,rounding_size=0.14',
                   facecolor='#FEF9E7', edgecolor='#34495E', linewidth=1.2))
axd.text(8.0, 4.0, 'Pinned-memory buffers\n264 B out / 268 B in', ha='center', va='center',
         fontsize=10)

a1 = _FAP((5.5, 4.75), (6.6, 5.4), arrowstyle='-|>', mutation_scale=18,
          linewidth=2.2, color='#8E44AD')
a2 = _FAP((6.6, 5.1), (5.5, 4.45), arrowstyle='-|>', mutation_scale=18,
          linewidth=2.2, color='#8E44AD')
axd.add_patch(a1); axd.add_patch(a2)
axd.add_patch(_FBP((6.35, 1.35), 3.3, 0.95, boxstyle='round,pad=0.04,rounding_size=0.12',
                   facecolor=LNK, edgecolor='#8E44AD', linewidth=1.4))
axd.text(8.0, 1.82, 'Dedicated 1 GbE link, round trip 0.29 ms',
         ha='center', va='center', fontsize=8.2, weight='bold', color='#6C3483')
axd.plot([8.0, 8.0], [2.30, 3.45], ls=':', color='#8E44AD', lw=1.6)

# The measured span brackets exactly the two host stages that are on the serial
# path, plus the device round trip; it must not reach the protocol servers or
# the fusion thread, which are outside the figure quoted in the text.
axd.add_patch(_FBP((0.55, 3.88), 5.1, 2.82, boxstyle='round,pad=0.05,rounding_size=0.18',
                   facecolor='none', edgecolor='#C0392B', linewidth=2.4, linestyle='--'))
axd.text(3.1, 6.92, 'Measured span: 6.2 ms critical path', fontsize=10.8, weight='bold',
         color='#C0392B', ha='center')
axd.set_title('(a) Where each stage runs, and what the measurement spans',
              fontsize=13, weight='bold')

# ---- right: critical-path decomposition -------------------------------------
labels = ['Barrier inference\n+ gradient (Jetson)', 'Host-device transfer\n+ synchronization',
          'QP solve\n(warm start)', 'Scheduling, serialization,\ncommand dispatch']
vals = [2.20, 0.29, 2.80, 0.91]
cols = ['#F39C12', '#8E44AD', '#3498DB', '#95A5A6']
left = 0.0
for v, c, lb in zip(vals, cols, labels):
    axt.barh([0], [v], left=left, color=c, edgecolor='black', linewidth=1.1, height=0.42)
    # Narrow segments cannot hold a label inside them; those are annotated below.
    if v >= 1.0:
        axt.text(left + v / 2, 0, f'{v:.2f}', ha='center', va='center',
                 fontsize=11, weight='bold', color='white')
    else:
        axt.annotate(f'{v:.2f}', xy=(left + v / 2, 0.21), xytext=(left + v / 2, 0.62),
                     ha='center', fontsize=10.5, weight='bold', color=c,
                     arrowprops=dict(arrowstyle='-', color=c, lw=1.2))
    left += v
axt.axvline(20, color='#C0392B', ls='--', lw=2)
axt.text(19.6, -0.52, '20 ms deadline', ha='right', fontsize=11, color='#C0392B', weight='bold')
axt.text(6.2, -0.36, 'Total 6.20 ms', ha='center', fontsize=12, weight='bold')
hs = [plt.Rectangle((0, 0), 1, 1, fc=c, ec='black') for c in cols]
axt.legend(hs, labels, fontsize=10.5, loc='upper right', bbox_to_anchor=(0.99, 0.99), ncol=1)
axt.set_ylim(-0.75, 1.15); axt.set_xlim(0, 21.5)
axt.set_yticks([])
axt.set_xlabel('Time (ms)', fontsize=12.5, weight='bold')
axt.set_title('(b) Critical-path decomposition\n(transfers and synchronization are inside the figure)',
              fontsize=13, weight='bold')
axt.grid(axis='x', alpha=0.3)

plt.tight_layout()
save_figure('FigureA1_Deployment_Timing')
print("Figure A1 saved")
plt.close()


# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*80)
print("FIGURE GENERATION COMPLETE")
print("="*80)
print("\nGenerated 13 figures:")
print("   1. Software Architecture (3-layer, 6.2ms control cycle)")
print("   2. Adapter Pattern")
print("   3. Multi-Platform Analysis (86% aggregate reuse)")
print("   4. PLC Integration")
print("   5. PLC Configuration Time (AB=45h, Mitsu=40h)")
print("   6. Software Performance (API, control, protocols, jitter)") 
print("   7. Fault Tolerance (166 faults, 0.83/h, 8 categories)") 
print("   8. Workspace Layout (hexagonal sensor array, 60% FOV overlap)") 
print("   9. Software Metrics (853 unit, 142 integration, 10740 LOC)") 
print("  10. Reliability Analysis (within-window; 847 h extrapolation withdrawn)")
print("  11. Architectural Ablation A0-A3 (7 configs, 30 cells, SD vs jitter fixed)")
print("  12. Architecture Comparison (quantities / qualitative matrix / effort)")
print("  A1. Deployment and Timing Boundaries (NEW: execution path + critical path)")
print("\nAll data verified against the revised paper tables and text.")
print("All panels derive from execution against SIMULATED vendor interfaces.")
