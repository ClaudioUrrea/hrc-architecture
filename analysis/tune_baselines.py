"""Baseline tuning sweep (Section 9.7; the sweep itself is deposited, the selected rows feed Table 12). New in v2.0.0.

Two reviewers objected, correctly, that the baselines of the first submission
were run at their published default parameters while the proposed controller had
been tuned on this workload. A comparison on those terms measures tuning effort,
not method.

Each baseline therefore received a matched budget: its principal parameter swept
over five values, with the configuration minimizing MEAN CYCLE TIME SUBJECT TO a
minimum separation of at least 150 mm selected on a TUNING SPLIT of 10 segments
held out from the 30 used for the comparison. All methods received the same
solver, the same 20 ms cycle budget and the same platform.

Tuning improved every baseline and removed two of the paper's claims. The
cycle-time advantage over DMPC falls from 1.3 s to 0.4 s and over SVO-CBF from
1.6 s to 0.7 s; neither approaches significance. The claim that survives is
about position on the safety-productivity frontier, not about throughput.

The residual limitation is stated in the paper and repeated here: each baseline
was tuned over ONE parameter, by the author of the competing method. A
specialist would likely do better. This is a comparison against competent
implementations under a common budget, not against the state of the art.

v2.1.0. The sweep, the selected values and the effect on the claims are now
recomputed from data/tuning_grid.parquet (10 tuning segments x 5 values x 6
baselines, plus the 30 comparison segments at the selected value) and
data/segments_30.parquet. The selection rule is APPLIED here, not asserted.
"""
import json
import numpy as np
import pyarrow.parquet as pq

import paired_stats

SELECTION_RULE = ("minimize mean cycle time subject to min separation >= 150 mm, "
                  "selected on a 10-segment tuning split disjoint from the "
                  "30 comparison segments")
MIN_SEP_MM = 150.0
GRID = "data/tuning_grid.parquet"
SEGMENTS = "data/segments_30.parquet"

SURVIVING_CLAIM = ("separation on the second endpoint: tuned DMPC reaches its "
                   "cycle time at a minimum separation 20 mm below the proposed "
                   "method's, so the defensible claim is about position on the "
                   "safety-productivity frontier, not about throughput")


def main(grid=GRID, segments=SEGMENTS):
    g = pq.read_table(grid).to_pandas()
    tun = g[g.split == "tuning"]
    sweep, selected = {}, {}
    for b, gb in tun.groupby("baseline", sort=False):
        agg = gb.groupby("value").agg(cycle_s=("cycle_time_s", "mean"), min_sep_mm=("min_separation_mm", "mean")).sort_index()
        feas = agg[agg.min_sep_mm >= MIN_SEP_MM]
        best = float(feas.cycle_s.idxmin())
        flagged = float(gb[gb.selected].value.iloc[0])
        assert abs(best - flagged) < 1e-9, f"{b}: stored selection {flagged} is not the rule's choice {best}"
        sweep[b] = {"parameter": gb.parameter.iloc[0], "values": [float(v) for v in agg.index],
                    "cycle_s": [round(float(v), 2) for v in agg.cycle_s],
                    "min_sep_mm": [round(float(v), 1) for v in agg.min_sep_mm], "selected": best}
        selected[b] = {"value": best, "cycle_s": round(float(agg.cycle_s[best]), 2),
                       "min_sep_mm": round(float(agg.min_sep_mm[best]), 1)}
        assert selected[b]["min_sep_mm"] >= MIN_SEP_MM
    ps = paired_stats.main(segments)
    eff = {}
    for b in ("DMPC", "SVO-CBF"):
        t = next(r for r in ps["tuned"] if r["baseline"] == b and r["endpoint"] == "cycle")
        u = next(r for r in ps["untuned"] if r["baseline"] == b and r["endpoint"] == "cycle")
        eff[b] = {"cycle_time_advantage_s_untuned": round(-u["delta"], 2),
                  "cycle_time_advantage_s_tuned": round(-t["delta"], 2),
                  "d_z_tuned": t["d_z"], "p_holm_tuned": round(t["p_holm"], 3),
                  "significant_after_tuning": bool(t["significant_at_005"])}
    return {"source": [grid, segments], "selection_rule": SELECTION_RULE,
            "tuning_split_segments": int(tun.segment_id.nunique()),
            "comparison_segments": ps["n_pairs"],
            "sweep": sweep, "selected": selected,
            "effect_on_the_papers_claims": eff,
            "claims_withdrawn_after_tuning": ["cycle-time advantage over DMPC",
                                              "cycle-time advantage over SVO-CBF"],
            "surviving_claim": SURVIVING_CLAIM,
            "limitation": "one parameter per baseline, tuned by the author of the "
                          "proposed method; competent implementations under a "
                          "common budget, not the state of the art"}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
