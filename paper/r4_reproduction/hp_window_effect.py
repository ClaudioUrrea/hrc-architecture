#!/usr/bin/env python3
"""Effect of the 105-s 'High performance' power-plan window (5 Nov 2026, 02:35:40-02:37:25 UTC, from the
Windows System log, event 12) on the fault-sensitivity run that was executing. Read-only: uses the
repository readers (manifest verified). Compares the window with equal-length windows and with the
30 min before and after, excluding cycles with injected overruns."""
import sys
from datetime import datetime, timezone
import numpy as np
sys.path.insert(0, "/opt/work/hrc31/analysis")
import hrc_logs as H  # noqa: E402

RUN = "/opt/work/hrc31/runs/2026-11-05T02-01-18.780Z_fault_sensitivity_weibull15_x1.0"
W0 = datetime(2026, 11, 5, 2, 35, 40, tzinfo=timezone.utc)
W1 = datetime(2026, 11, 5, 2, 37, 25, tzinfo=timezone.utc)
from pathlib import Path
d = Path(RUN)
m = H.manifest(d)
assert m["status"] == "complete", m["status"]
c = H.cycles(d)
start = datetime.strptime(m["start_utc"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
mono0 = m["start_mono_ns"]
to_mono = lambda t: mono0 + int((t - start).total_seconds() * 1e9)
tw = c["t_wake_ns"].astype(np.int64)
e = H.exec_ms(c)
inj = H.flag(c, "injected_overrun")
miss = H.deadline_miss(c, H.period_ns(d))
ri = np.r_[np.nan, H.release_interval_ms(c)]
late = H.flag(c, "release_late")
stop = np.isin(c["mode"], [5, 6, 7])


def summ(a, b, label):
    sel = (tw >= a) & (tw < b)
    ok = sel & ~inj & np.isfinite(e)
    rk = sel & ~late & np.isfinite(ri)
    if ok.sum() == 0:
        return
    x = e[ok]
    print(f"{label:34s} cycles={int(sel.sum()):6d} exec med={np.median(x)*1000:7.1f}us p99={np.percentile(x,99)*1000:7.1f}us "
          f"max={x.max():6.3f}ms relSD={np.std(ri[rk], ddof=1)*1000:6.1f}us misses(ret)={int((miss & sel & ~inj).sum())} "
          f"stop%={100*stop[sel].mean():5.1f}")


a, b = to_mono(W0), to_mono(W1)
L = b - a
print(f"run {d.name}: {len(c)} cycles; window {W0:%H:%M:%S}-{W1:%H:%M:%S} UTC ({L/1e9:.0f} s)")
summ(a, b, "HIGH PERFORMANCE window")
for k in (1, 2, 3):
    summ(a - k * L, b - k * L, f"{k} window(s) before")
    summ(a + k * L, b + k * L, f"{k} window(s) after")
summ(a - 1800e9, a, "30 min before")
summ(b, b + 1800e9, "30 min after")
summ(tw[0], tw[-1] + 1, "whole run")
# rank of the window median among all 105-s windows of the run
edges = np.arange(tw[0], tw[-1], L)
meds = []
for s0 in edges:
    sel = (tw >= s0) & (tw < s0 + L) & ~inj & np.isfinite(e)
    if sel.sum() > 1000:
        meds.append(np.median(e[sel]))
wsel = (tw >= a) & (tw < b) & ~inj & np.isfinite(e)
wm = np.median(e[wsel])
print(f"window median {wm*1000:.1f} us; among {len(meds)} consecutive {L/1e9:.0f}-s windows of the run: "
      f"min {min(meds)*1000:.1f}, median {np.median(meds)*1000:.1f}, max {max(meds)*1000:.1f} us; "
      f"rank {sum(1 for v in meds if v < wm) + 1}/{len(meds)}")
