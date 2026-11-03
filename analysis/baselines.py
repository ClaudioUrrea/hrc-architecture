"""Baseline tuning (selection rule fixed in advance) and the paired comparison.

Release 3.1: the comparison includes pf_ssm (potential field under the shared SSM limit), so the
confirmatory family is 4 baselines x 2 endpoints = 8 paired tests, Holm-adjusted together. The
tuning rule is unchanged (estimated separation never below the floor on any tuning segment;
shortest mean task cycle). The minimum TRUE separation (simulator ground truth) is reported as
a secondary endpoint with paired confidence intervals, outside the Holm family. No equivalence
or non-inferiority claim is made from a non-significant difference."""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import hrc_logs as H
from stats import holm, paired

FLOOR = 0.15


def _segment(d):
    ev = H.events(d)
    tc = [e["value"] for e in ev if e["text"] == "task_cycle"]
    c = H.cycles(d)
    avail = ~H.flag(c, "estimate_unavailable")
    sep = c["min_sep_m"][avail & (c["min_sep_m"] > -1)]
    out = {"task_cycle_s": float(np.mean(tc)) if tc else None, "task_cycles": len(tc),
           "min_sep_m": float(sep.min()) if len(sep) else None}
    if "gt_min_sep_m" in c.dtype.names:  # 3.1 records
        gt = c["gt_min_sep_m"][np.isfinite(c["gt_min_sep_m"])]
        out["gt_min_sep_m"] = float(gt.min()) if len(gt) else None
    return out


def tune(root, out_path=None):
    runs = H.runs(root, "tuning")
    if not runs:
        return None
    res = defaultdict(lambda: defaultdict(list))
    meta = {}
    for d in runs:
        t = H.config(d)["tuning"]
        res[t["strategy"]][t["value"]].append(_segment(d))
        meta[t["strategy"]] = t["parameter"]
    sel = {}
    for strat, vals in res.items():
        best = None
        for v, segs in vals.items():
            cyc = [s["task_cycle_s"] for s in segs if s["task_cycle_s"]]
            seps = [s["min_sep_m"] for s in segs if s["min_sep_m"] is not None]
            if not cyc or not seps or min(seps) < FLOOR:   # rule: never crosses the floor on any tuning segment
                continue
            m = float(np.mean(cyc))
            if best is None or m < best["mean_task_cycle_s"]:
                gts = [s["gt_min_sep_m"] for s in segs if s.get("gt_min_sep_m") is not None]
                best = {"parameter": meta[strat], "value": v, "mean_task_cycle_s": m, "min_sep_m": min(seps), "segments": len(segs),
                        "min_true_sep_m": min(gts) if gts else None}
        if best:
            sel[strat] = best
    if out_path:
        Path(out_path).write_text(json.dumps(sel, indent=2))
    return sel


def compare(root):
    runs = H.runs(root, "baseline_compare")
    if not runs:
        return None
    seg = defaultdict(dict)
    for d in runs:
        cfg = H.config(d)["compare"]
        seg[cfg["strategy"]][cfg["segment"]] = _segment(d)
    if "proposed" not in seg:
        return {"error": "no proposed runs"}
    rows = []
    for strat in [s for s in seg if s != "proposed"]:
        common = sorted(set(seg["proposed"]) & set(seg[strat]))
        for ep, key in (("task_cycle_s", "task_cycle_s"), ("min_sep_m", "min_sep_m")):
            pairs = [(seg["proposed"][k][key], seg[strat][k][key]) for k in common
                     if seg["proposed"][k][key] is not None and seg[strat][k][key] is not None]
            if len(pairs) < 3:
                continue
            a, b = map(np.array, zip(*pairs))
            r = paired(a, b)
            r.update({"endpoint": ep, "baseline": strat, "proposed_mean": float(a.mean()), "proposed_sd": float(a.std(ddof=1)),
                      "baseline_mean": float(b.mean()), "baseline_sd": float(b.std(ddof=1))})
            rows.append(r)
    adj = holm([r["p"] for r in rows])
    for r, p in zip(rows, adj):
        r["p_holm"] = float(p)
    secondary = []
    for strat in [s for s in seg if s != "proposed"]:
        common = sorted(set(seg["proposed"]) & set(seg[strat]))
        pairs = [(seg["proposed"][k].get("gt_min_sep_m"), seg[strat][k].get("gt_min_sep_m")) for k in common]
        pairs = [p for p in pairs if p[0] is not None and p[1] is not None]
        if len(pairs) < 3:
            continue
        a, b = map(np.array, zip(*pairs))
        r = paired(a, b)
        r.update({"endpoint": "true_min_sep_m", "baseline": strat, "proposed_mean": float(a.mean()),
                  "baseline_mean": float(b.mean()), "note": "secondary, outside the Holm family"})
        secondary.append(r)
    return {"hypotheses": len(rows), "rows": rows, "secondary_true_separation": secondary,
            "interpretation": "a non-significant difference is not evidence of equivalence; no margin is defined"}
