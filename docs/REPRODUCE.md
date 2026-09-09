# Reproducing the results

This file is the machine-readable companion to Table 4 of the manuscript. Every
row states which configuration, script and data file produce a reported result.

| Paper item | Configuration | Script | Data |
|---|---|---|---|
| Control-cycle timing (Fig. 6b, §9.2) | `cfg/rt_nominal.yaml` | `analysis/timing.py` | `data/cycles_36M.parquet` |
| API and protocol latency (Fig. 6a,c,d, §6.2) | `cfg/protocol_bench.yaml` | `analysis/protocol.py` | `data/protocol_samples.parquet` |
| Code metrics (Fig. 3a,c, §5.2) | — | `analysis/code_metrics.sh` | `data/cloc_lizard.json` |
| Porting effort (Fig. 3b, §5.3, App. C) | — | `analysis/effort.py` | `data/effort_log.csv` |
| PLC commissioning (Fig. 5, Table 6, §6.1) | `cfg/plc_*.yaml` | `analysis/plc_time.py` | `data/plc_runs.csv` |
| Fault campaign and availability (Fig. 7, Table 7, §8) | `cfg/fault_inject.yaml` | `analysis/faults.py` | `data/faults_450.csv` |
| Reliability (Fig. 10, §9.5) | — | `analysis/reliability.py` | `data/interfailure.csv` |
| Architectural ablation (Fig. 11, Table 9, §9.6) | `cfg/ablation_A{0..3}.yaml` | `analysis/ablation.py` | `data/ablation_cycles.parquet` |
| Baseline comparison (Table 10, §9.7) | `cfg/baseline_*.yaml` | `analysis/paired_stats.py` | `data/segments_30.parquet` |
| CBF training and evaluation (§7.2) | `cfg/cbf_train.yaml` | `train/cbf_train.py` | `data/cbf_dataset_66d.npz` |

## Steps

```bash
git clone https://github.com/ClaudioUrrea/hrc-architecture
cd hrc-architecture
python -m pip install -r requirements.txt
make fetch-data          # pulls the two large parquet files from Figshare
make all                 # writes out/results.json and out/figures/
make check               # asserts every recomputed value matches the paper
```

`make check` is the important one. It recomputes fourteen headline quantities —
the serial critical path, the rule-of-three deadline-miss bound, the PLC
commissioning means, the fault-population counts, availability, all three MTBF
estimates, the fitted Weibull shape and the architectural cost — and exits
non-zero if any of them disagrees with the value printed in the manuscript.

## Determinism

`config/seeds.json` holds the master seed (20260215) and every derived
per-scenario, per-injection, per-ablation and per-bootstrap seed. Re-running any
script with the deposited seeds reproduces the deposited data bit for bit on the
same NumPy version pinned in `requirements.txt`.

## Scope, again

The endpoints exercised are vendor **software simulators**: URSim 5.17.0, KUKA
Sunrise.OS 1.17 in FRI monitoring mode, ABB RobotStudio 2024.1 virtual
controller, Siemens PLCSIM Advanced V5.0, Rockwell Logix Emulate V33 and
Mitsubishi GX Simulator3, with cell kinematics from CoppeliaSim 4.6.0 rev18. No
physical equipment and no human participant was involved. Timing figures exclude
physical actuation, true sensor acquisition and electromagnetic interference on
industrial buses.
