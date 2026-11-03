#!/usr/bin/env python3
"""Generate the configuration files of every experiment campaign from cfg/base_sim_ur5e.json.

The generated files are the pre-registered design: they are written (and should be committed)
before any campaign runs, so the design cannot drift towards the results. Each campaign
directory gets plan.csv with one row per run and its expected duration.

    python3 tools/make_campaigns.py all                 # every campaign below, default sizes
    python3 tools/make_campaigns.py timing --blocks 120 --block-minutes 100
    python3 tools/make_campaigns.py ablation
    python3 tools/make_campaigns.py tuning
    python3 tools/make_campaigns.py compare --selection runs/<...>/tuning_selection.json
    python3 tools/make_campaigns.py injection
    python3 tools/make_campaigns.py sensitivity
    python3 tools/make_campaigns.py calibration          # 3.1: position-uncertainty calibration runs

Release 3.1 (Reviewer 2, round 4):
  * calibration: six 10-min runs (S1-S6, proposed strategy, no faults, position margin 0) that
    measure the error of the fused human estimate against the simulator ground truth; the rule
    in tools/calibrate_position_margin.py turns them into control.position_margin and ssm.Z_d
    BEFORE the other campaigns are generated (see docs/PREREGISTRATION_3.1.md);
  * pf_ssm: the potential-field baseline under the same SSM speed limit as the other strategies,
    tuned and compared like the others (tuning grid of pf);
  * ablation: ground-truth probe disabled (logging.ground_truth = false), so that the timing
    ablation has no evaluation thread that release 3.0 did not have.
"""
import argparse
import copy
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASE = json.loads((ROOT / "cfg" / "base_sim_ur5e.json").read_text())
OUT = ROOT / "cfg" / "campaigns"
LIMIT = 0

SCENARIOS = {  # name: (task-cycle seconds of the scripted operator)
    "S1": ("pick_and_place", 18), "S2": ("screwdriving", 25), "S3": ("inspection", 35),
    "S4": ("material_handling", 22), "S5": ("mixed", 28), "S6": ("continuous", 20),
}
# Design fault rates per hour for campaigns that run with background faults. These are design
# parameters chosen to exercise every detection path during the campaign; they are not claims
# about field failure rates (see cfg/fault_rates.md).
DESIGN_RATES = {"tracking_loss": 0.35, "sensor_timeout": 0.18, "computational_overrun": 0.12,
                "hardware_communication": 0.08, "configuration_inconsistency": 0.05,
                "network_partition": 0.03, "constraint_violation": 0.02, "memory_allocation": 0.0}


def cfg(experiment, variant, seed, duration_s, scenario="S1"):
    c = copy.deepcopy(BASE)
    c["experiment"], c["variant"], c["seed"], c["duration_s"] = experiment, variant, int(seed), float(duration_s)
    name, cyc = SCENARIOS[scenario]
    c["human"]["scenario"], c["human"]["cycle_s"] = name, cyc
    c["scenario_id"] = scenario
    return c


def write(campaign, configs):
    d = OUT / campaign
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.json"):
        old.unlink()
    rows = []
    if LIMIT:
        configs = configs[:: max(1, len(configs) // LIMIT)][:LIMIT]
    for c in configs:
        f = d / f"{c['variant']}.json"
        f.write_text(json.dumps(c, indent=2))
        rows.append({"config": str(f.resolve().relative_to(ROOT)) if f.resolve().is_relative_to(ROOT) else str(f.resolve()), "variant": c["variant"], "scenario": c.get("scenario_id", ""),
                     "seed": c["seed"], "duration_s": c["duration_s"]})
    with open(d / "plan.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    hours = sum(r["duration_s"] for r in rows) / 3600
    print(f"{campaign}: {len(rows)} runs, {hours:.1f} h of run time -> {d}")


def timing(a):
    rng = np.random.default_rng(a.seed)
    weights = {"S1": 24, "S2": 21, "S3": 18, "S4": 24, "S5": 18, "S6": 15}
    total = sum(weights.values())
    assign = []
    for s, k in weights.items():
        assign += [s] * round(k * a.blocks / total)
    assign = (assign + ["S1"] * a.blocks)[: a.blocks]
    rng.shuffle(assign)  # randomised block order
    out = []
    for i, s in enumerate(assign):
        c = cfg("timing_campaign", f"block_{i + 1:03d}", a.seed * 1000 + i, a.block_minutes * 60, s)
        c["faults"]["enabled"] = True
        c["faults"]["rates_per_h"] = dict(DESIGN_RATES)
        c["background_load"] = {"threads": 2, "duty": float(np.round(rng.uniform(0.2, 0.4), 3))}
        out.append(c)
    write("timing", out)


ABLATION = {
    "A0": {"architecture": "monolithic"},
    "A1": {"rt.transport": "socket"},
    "A2a": {"rt.policy": "other"},
    "A2b": {"rt.shared_core": True},
    "A2c": {"watchdog.enabled": False},
    "A2": {"rt.policy": "other", "rt.shared_core": True, "watchdog.enabled": False},
    "A3": {},
}


def setp(c, path, v):
    keys = path.split(".")
    for k in keys[:-1]:
        c = c[k]
    c[keys[-1]] = v


def ablation(a):
    out = []
    for name, mods in ABLATION.items():
        for seed in range(1, 6):
            for scen in ("S1", "S2", "S4"):
                for load in ("idle", "load"):
                    c = cfg("ablation", f"{name}_seed{seed}_{scen}_{load}", a.seed + 100 * seed, a.cycles * 0.02, scen)
                    for k, v in mods.items():
                        setp(c, k, v)
                    c["background_load"] = {"threads": 2 if load == "load" else 0, "duty": 0.4}
                    c["ablation"] = {"configuration": name, "seed_index": seed, "load": load}
                    c["logging"]["ground_truth"] = False  # 3.1: no evaluation thread in the timing ablation
                    out.append(c)
    write("ablation", out)


TUNING = {  # principal parameter of each method and its five candidate values
    "proposed": ("control.kappa", [2.0, 3.0, 4.0, 6.0, 8.0]),
    "hc_cbf": ("control.kappa", [2.0, 3.0, 4.0, 6.0, 8.0]),
    "ssm": ("ssm.C", [0.10, 0.15, 0.20, 0.25, 0.30]),
    "pf": ("pf.k_rep", [0.02, 0.04, 0.08, 0.12, 0.16]),
    "pf_ssm": ("pf.k_rep", [0.02, 0.04, 0.08, 0.12, 0.16]),  # 3.1
}


def tuning(a):
    out = []
    for strat, (param, values) in TUNING.items():
        for vi, v in enumerate(values):
            for seg in range(1, a.tuning_segments + 1):
                scen = ("S1", "S2", "S3")[(seg - 1) % 3]
                c = cfg("tuning", f"{strat}_v{vi}_seg{seg:02d}", 900000 + seg, a.segment_minutes * 60, scen)
                c["control"]["strategy"] = strat
                c["control"]["learned"]["enabled"] = strat == "proposed"
                setp(c, param, v)
                c["tuning"] = {"strategy": strat, "parameter": param, "value": v, "segment": seg}
                out.append(c)
    write("tuning", out)


def compare(a):
    sel = json.loads(Path(a.selection).read_text()) if a.selection else {}
    if not sel:
        print("compare: no --selection given; using base parameters (untuned)")
    out = []
    for strat in TUNING:
        for seg in range(1, a.segments + 1):
            scen = ("S1", "S2", "S3")[(seg - 1) % 3]
            c = cfg("baseline_compare", f"{strat}_seg{seg:02d}", 500000 + seg, a.segment_minutes * 60, scen)
            c["control"]["strategy"] = strat
            c["control"]["learned"]["enabled"] = strat == "proposed"
            if strat in sel:
                setp(c, sel[strat]["parameter"], sel[strat]["value"])
            c["compare"] = {"strategy": strat, "segment": seg, "tuned": strat in sel}
            out.append(c)
    write("compare", out)


def injection(a):
    out = []
    per_cat = a.injections / 8 / a.injection_hours  # per hour per category
    for i in range(a.injection_runs):
        c = cfg("fault_injection", f"inj_{i + 1:02d}", 700000 + i, a.injection_hours * 3600 / a.injection_runs,
                ("S1", "S2", "S3", "S4", "S5", "S6")[i % 6])
        c["faults"]["enabled"] = True
        c["faults"]["rates_per_h"] = {k: per_cat for k in DESIGN_RATES}
        c["operator"]["ack_median_s"] = 60
        out.append(c)
    write("injection", out)


def sensitivity(a):
    out = []
    models = [("poisson", {}), ("clustered", {"mean_cluster_size": 3.0, "cluster_spread_s": 30.0}),
              ("weibull07", {"arrival": "weibull", "weibull_shape": 0.7}), ("weibull15", {"arrival": "weibull", "weibull_shape": 1.5})]
    for mname, mods in models:
        for scale in (0.5, 1.0, 1.5):
            c = cfg("fault_sensitivity", f"{mname}_x{scale}", 800000, a.sensitivity_hours * 3600, "S1")
            c["faults"].update({"enabled": True, "arrival": mods.get("arrival", mname if mname != "weibull07" else "weibull"),
                                "rate_scale": scale, "rates_per_h": dict(DESIGN_RATES)})
            c["faults"].update({k: v for k, v in mods.items() if k != "arrival"})
            # higher rates so that a few hours contain enough events; the scale factor is relative
            c["faults"]["rates_per_h"] = {k: v * 20 for k, v in DESIGN_RATES.items()}
            out.append(c)
    write("sensitivity", out)


def calibration(a):
    out = []
    for i, scen in enumerate(("S1", "S2", "S3", "S4", "S5", "S6")):
        c = cfg("calibration", f"cal_{scen}", 600000 + i, a.calibration_minutes * 60, scen)
        c["control"]["strategy"] = "proposed"
        c["control"]["position_margin"] = 0.0
        c["faults"]["enabled"] = False
        c["calibration"] = {"purpose": "estimate error vs ground truth; input of tools/calibrate_position_margin.py"}
        out.append(c)
    write("calibration", out)


def main():
    global OUT, BASE, LIMIT
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["all", "timing", "ablation", "tuning", "compare", "injection", "sensitivity",
                                     "calibration"])
    ap.add_argument("--seed", type=int, default=20261012)
    ap.add_argument("--blocks", type=int, default=120)
    ap.add_argument("--block-minutes", type=float, default=100)
    ap.add_argument("--cycles", type=int, default=10000)
    ap.add_argument("--segments", type=int, default=30)
    ap.add_argument("--tuning-segments", type=int, default=10)
    ap.add_argument("--segment-minutes", type=float, default=20)
    ap.add_argument("--selection", default="")
    ap.add_argument("--injections", type=int, default=480)
    ap.add_argument("--injection-hours", type=float, default=10)
    ap.add_argument("--injection-runs", type=int, default=10)
    ap.add_argument("--sensitivity-hours", type=float, default=2)
    ap.add_argument("--calibration-minutes", type=float, default=10)
    ap.add_argument("--out", default=str(OUT), help="output directory (default cfg/campaigns)")
    ap.add_argument("--base", default=str(ROOT / "cfg" / "base_sim_ur5e.json"))
    ap.add_argument("--limit", type=int, default=0, help="pilot only: keep the first N runs of each campaign")
    a = ap.parse_args()
    OUT = Path(a.out)
    BASE = json.loads(Path(a.base).read_text())
    LIMIT = a.limit
    # `compare` is generated only after tuning, from the selection file (see docs/RUNBOOK.md)
    todo = ["timing", "ablation", "tuning", "injection", "sensitivity"] if a.what == "all" else [a.what]
    for t in todo:
        globals()[t](a)


if __name__ == "__main__":
    main()
