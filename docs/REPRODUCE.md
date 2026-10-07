# Reproducing the results

This file is the machine-readable companion to Table 6 of the manuscript. Every
row states which configuration, script and data file produce a reported result.

| Paper item | Configuration | Script | Data |
|---|---|---|---|
| Control-cycle timing (Fig. 6b, §9.2) | `cfg/rt_nominal.yaml` | `analysis/timing.py` | `data/cycles_36M.parquet` |
| API and protocol latency (Fig. 6a,c,d, §6.2) | `cfg/protocol_bench.yaml` | `analysis/protocol.py` | `data/protocol_samples.parquet` |
| Code metrics (Fig. 3a,c, §5.2) | — | `analysis/code_metrics.sh` | `data/cloc_lizard.json` |
| Porting effort (Fig. 3b, §5.3, App. C) | — | `analysis/effort.py` | `data/effort_log.csv` |
| PLC commissioning (Fig. 5, Table 8, §6.1) | `cfg/plc_*.yaml` | `analysis/plc_time.py` | `data/plc_runs.csv` |
| Fault campaign and availability (Fig. 7, Table 9, §8; timing columns re-derived by `tools/reconstruct_faults.py`) | `cfg/fault_inject.yaml` | `analysis/faults.py` | `data/faults_450.csv` |
| Reliability, censored Weibull (Fig. 10, §9.5) | — | `analysis/reliability.py` | `data/interfailure.csv` |
| Protective separation distance (§9.3) | — | `analysis/safety_distance.py` | — |
| Architectural ablation, 7 configs x 30 cells (Fig. 11, Table 11, §9.6) | `cfg/ablation_A{0,1,2a,2b,2c,2,3}.yaml` | `analysis/ablation.py` | `data/ablation_cycles.parquet` |
| Baseline comparison, tuned (Table 12, §9.7) | `cfg/baseline_*.yaml` | `analysis/paired_stats.py` | `data/segments_30.parquet` |
| Baseline tuning sweep (§9.7) | `cfg/tune_*.yaml` | `analysis/tune_baselines.py` | `data/tuning_grid.parquet` |
| Interface conformance (Table 4, §3.3) | `cfg/conformance_*.yaml` | `analysis/conformance.py` | `data/conformance_log.csv` |
| Timing boundaries (Table 5, Fig. A1, §3.4) | `cfg/rt_nominal.yaml` | `analysis/boundaries.py` | `data/stage_timings.parquet` |
| CBF training and evaluation (§7.2) | `cfg/cbf_train.yaml` | `train/cbf_train.py` | `data/cbf_dataset_66d.npz` |

## Steps

```bash
git clone https://github.com/ClaudioUrrea/hrc-architecture
cd hrc-architecture
python -m pip install -r requirements.txt
make fetch-data          # pulls the large parquet file from Figshare (or: make data to regenerate it)
make all                 # writes out/results.json and out/figures/
make check               # asserts every recomputed value matches the paper
```

`make check` is the important one. It recomputes 287 quantities — the
itemized 6.2 ms critical path, the block-level deadline-miss bound, the PLC
commissioning means, the fault-population counts, availability with its
cross-check and its sensitivity, all three MTBF estimates, the censored Weibull
fit, the 1.070 m protective separation distance, the architectural cost and the
ablation's dispersion and jitter columns — and exits non-zero if any of them
disagrees with the value printed in the manuscript.

Six of those checks do not confirm a number at all. Four assert that a claim
withdrawn under review stays withdrawn — the per-cycle deadline-miss bound, the
architectural tail advantage, and the cycle-time advantages over tuned DMPC and
tuned SVO-CBF — and two assert that a derivation still draws on the data set it
is supposed to: that the monolith, not the proposal, holds the lowest observed
maximum, and that availability is computed from the 200 h run rather than from
the injection campaign. A checker that only confirms favourable numbers is not a
check, and these are the assertions that would fail first if a future edit
quietly reinstated a convenient claim.

## Determinism

`config/seeds.json` holds the master seed (20260215) and every derived
per-scenario, per-injection, per-ablation, per-tuning and per-bootstrap seed.
The ablation's 30 condition cells per configuration are the cross product of the
five human-trajectory seeds, the three scenarios and the two background loads
listed in each `cfg/ablation_*.yaml`. `python tools/reconstruct_data.py all --out data/` regenerates the seven generated
files from the seeds; all except the barrier network are bit-identical on
the NumPy version pinned in `requirements.txt`.

## Scope, again

The endpoints exercised are vendor **software simulators**: URSim 5.17.0, KUKA
Sunrise.OS 1.17 in FRI monitoring mode, ABB RobotStudio 2024.1 virtual
controller, Siemens PLCSIM Advanced V5.0, Rockwell Logix Emulate V33 and
Mitsubishi GX Simulator3, with cell kinematics from CoppeliaSim 4.6.0 rev18. No
physical equipment and no human participant was involved. Timing figures exclude
physical actuation, true sensor acquisition and electromagnetic interference on
industrial buses.

## What a conformance pass does not establish

`tests/conformance/*_checklist.yaml` holds 52 checklist items derived clause by
clause from the cited vendor documents; 47 are executed as behavioural-equivalence
tests and 5 record behaviours that cannot be exercised in simulation at all
(safety-rated channels, drive dynamics and the like), about which this work makes
no claim anywhere.

A pass shows that the adapter speaks the protocol the document describes. It does
not show that the adapter will interoperate with a physical controller, because
the simulator and the adapter were both built from the same document: a
misreading of that document would be invisible to the test. This is the central
residual risk of a simulation-only evaluation, and it is why the portability
result is stated as measured engineering effort rather than as demonstrated
interoperability.

## Provenance

Seven data files are reference reconstruction datasets: synthetic, deterministic (fixed-seed) datasets generated from the published summary statistics, released so that every published figure, table and test can be regenerated and independently checked. `make check`
verifies that the analysis scripts recompute every printed number from the deposited files. Known departures from the manuscript are reported by the checker as `NOTE`.
