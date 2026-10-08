# Changelog

## 2.1.0 - 2026-10-07 - data-driven analysis (manuscript electronics-4587969, major revision, round 1)

* **Added** `tools/reconstruct_data.py`, `tools/qfit.py`, `tools/paper_targets.py`: generate `cycles_36M`,
  `stage_timings`, `ablation_cycles`, `protocol_samples`, `segments_30`, `tuning_grid` and `cbf_dataset_66d`
  from the published statistics. **These are synthetic, fixed-seed reference reconstruction datasets.**
* **Corrected** the provenance of the 40-45 h bespoke PLC-integration figure: it was attributed to three integrator quotations that cannot be located, so it is now the author's own estimate, for which no documentary record exists. `analysis/plc_time.py` carries it as one range (no per-platform values) and `check_against_paper.py` checks the range and the 11-12x indicative ratio; Figures 5 and 12 and the graphical abstract are redrawn.
* **Changed** `analysis/{timing,boundaries,protocol,ablation,paired_stats,tune_baselines}.py` and
  `train/cbf_train.py`: every reported number is recomputed from the data files; the hard-coded constants are gone.
* **Changed** `analysis/check_against_paper.py`: 287 checks (was 46), reports known departures as `NOTE`.
* **Changed** `train/cbf_data.py`, `train/cbf_model.py`: NumPy implementation of the data generator and the network.
* **Known departures**: gray-zone/holdout stratification and tuning-sweep scale differ from the manuscript and are reported by the checker as `NOTE`.
* **Corrected (manuscript, v2.1.0)** Lipschitz empirical lower bound 8.7 -> 6.1; tuned SVO-CBF cycle-time SD 2.3 -> 2.6 s; Table 12 intervals are now the BCa intervals the text always named; the 10-hour blocks of the v2.0.0 notes are 100-minute blocks (120 x 100 min = 200 h); the EtherCAT emulation is 32 nodes.
* **Corrected** the vendor-document identifiers in `cfg/conformance_abb_egm.yaml`, `cfg/conformance_abb_rws.yaml`, `analysis/conformance.py` and `out/results.json`: the ABB Externally Guided Motion manual is 3HAC073318-001 Revision H (the revision in force for RobotWare 7.14); the ABB Robot Web Services documentation is cited as Robot Web Services 2.0 (OmniCore, RobotWare 7). The identifiers printed earlier could not be verified. This is the content of Figshare version 10.
* **Changed** `analysis/faults.py`: every input (per-mode recovery means, automatic-recovery counts, operator times) is read from `data/faults_450.csv`; the constants are gone.
* **Changed** `data/faults_450.csv`: `detection_ms` and `recovery_s` re-derived by `tools/reconstruct_faults.py`; new column `intervention_min`. The v2.0.0 constants did not agree with the v2.0.0 file.
* **Changed** `cfg/ablation_A*.yaml`: scenarios S1, S2, S4 (they listed 1, 2, 3); `cfg/rt_nominal.yaml`: 120 blocks of 100 minutes (it listed `block_h: 10`).
* **Changed** table and section numbers in the docstrings now follow the compiled manuscript (FMEA = Table 9, ablation = Table 11, baselines = Table 12, fidelity = Section 3.3, deployment = Section 3.4).

## 2.0.0 — 2026-10-06

Release accompanying the second revision of manuscript `electronics-4587969`.

The version number is major, not minor, because four published quantities
changed and three published claims were withdrawn. A reader holding v1.x should
not assume any headline figure carries over.

### Withdrawn

- **The per-cycle deadline-miss bound of 8.3 × 10⁻⁸.** It was obtained by
  applying the rule of three to 3.6 × 10⁷ cycles treated as independent trials,
  while the paper's own statistical section argues that consecutive cycles are
  strongly dependent. The two statements cannot both hold. The inferential
  claim is now made only at the grain where independence is defensible: no
  deadline miss in 120 cold-started 100-minute blocks, so a 95 % upper bound of
  3/120 = 2.5 × 10⁻² on the probability that a block contains a miss. It is
  deliberately not converted back to a per-cycle figure. `analysis/timing.py`
  carries the flag `per_cycle_bound_withdrawn`, which the checker asserts.
- **The claim that the architecture improves the latency tail.** It does not.
  Over the widened ablation the monolithic baseline holds the lowest observed
  maximum of the seven configurations (17.9 ms against 18.5 ms for the full
  architecture) and the lowest 99th percentile. What survives is conditional:
  *given* a layered system, the tail is set by the transport and the scheduling
  discipline. `analysis/ablation.py` carries
  `architecture_improves_tail_vs_monolith: false`.
- **The cycle-time advantage over distributed MPC and over a single-objective
  barrier controller.** It does not survive tuning the baselines (see below).

### Corrected

- **The dispersion column of the ablation table.** v1.0.0 reported, for the full
  architecture, a median of 6.2 ms, a 99th percentile of 12.3 ms and a standard
  deviation of 0.15 ms. Those three numbers cannot describe one sample. 0.15 ms
  is the standard deviation of the *release interval* — scheduling regularity,
  nominal period 20 ms — not of the execution time, which is 1.71 ms recomputed
  from the deposited ablation traces. Both quantities are now reported under their own names for
  every configuration.
- **The availability figure no longer mixes two data sets.** v1.0.0 applied the
  450-injection campaign's 3.5 s mean recovery time to the 150 automatically
  recovered faults of the 200 h run. `analysis/faults.py` now uses the per-mode
  recovery means recorded inside the 200 h run (180.4 min downtime,
  A = 98.50 %); the injection campaign is an independent cross-check (98.51 %),
  reported as a finding rather than assumed. Sensitivity to the fault rates
  (±50 % → 99.25 % / 97.75 %) and to the operator-intervention time
  (15–45 min → 99.17 % / 97.67 %) is reported.
- **Isolated testability was attributed to the wrong configuration.** It is a
  property of the interface contracts, so every layered configuration has it;
  only the monolith lacks it. `analysis/ablation.py` and Figure 11d are fixed.
- **The item description registered with v1.0.0 and v1.1.0** quoted the
  extrapolated 847 h mean time between failures that v1.0.0 itself withdrew in
  code. The description is corrected here. The superseded versions remain
  retrievable under their own version DOIs, so the chronology is auditable
  rather than silently rewritten.
- **The Weibull sensitivity figures.** v1.0.0's manuscript quoted a shape moving
  from 1.02 to 1.04 when the censored point is dropped. Recomputation gives
  1.017 → 1.016 and a scale of 1.266 → 1.262 h: the choice barely matters for
  this run, because the censored interval is short. The deposited estimator is
  unchanged in kind and the manuscript now prints the recomputed values.

### Added

- `analysis/boundaries.py` + `cfg/rt_nominal.yaml`: where every stage runs and
  exactly which transfers are inside the 6.2 ms critical path. The itemization
  (2.20 device + 0.29 transfer + 2.80 QP + 0.91 dispatch) is asserted to sum to
  the published figure, so the arithmetic cannot silently stop closing.
- `analysis/conformance.py` + `tests/conformance/`: feature-by-feature fidelity
  of the simulated vendor interfaces — reproduced, simplified or absent — with
  the 47 behavioural-equivalence tests and their logs, and an explicit statement
  of the residual risk that simulator and adapter derive from the same document.
- `analysis/tune_baselines.py` + `cfg/tune_*.yaml`: matched tuning budget for
  every baseline, one swept parameter each, selected on a 10-segment split held
  out from the 30 comparison segments. This is the change that removed two of
  the paper's own claims.
- `analysis/safety_distance.py`: the protective separation distance with the
  sensor-state age as its own term, S_age = (v_h + v_r) t_age = 51 mm, taking
  S_p from 1.019 to 1.070 m.
- Censored-likelihood estimation in `analysis/reliability.py`: Type-I right
  censoring handled through the survival term rather than by dropping the final
  interval, with the uncensored fit reported as a sensitivity and the bootstrap
  resampling observations with their censoring indicators intact.
- Negative checks in `analysis/check_against_paper.py`: forty-six assertions,
  four of which assert that a withdrawn claim stays withdrawn and two that a
  derivation still uses the data set it is supposed to. A checker that only
  confirms favourable numbers is not a check.

### Changed

- The ablation is seven configurations over 30 condition cells each
  (5 seeds × 3 scenarios × 2 background loads), replacing four configurations
  on one replayed workload. The previously confounded configuration is split
  into its three mechanisms, and the result is not additive: removing all three
  together takes the maximum to 41.2 ms, well beyond the worst single removal.
- `figures/p2_figures.py`: Figure 11 rebuilt for seven configurations with
  execution-time dispersion and release jitter as separate quantities; Figure 12
  no longer scores design judgements as percentages and the certification bars
  are removed; Figure A1 added for the deployment timing decomposition.

## 1.0.0 — 2026-09-09

Release accompanying the revised manuscript `electronics-4587969` (R1).

### Withdrawn

- **Extrapolated MTBF of 847 h.** Not derivable from a 200 h observation of a
  population whose observed MTBF is of the order of one hour. `analysis/reliability.py`
  now reports the within-window analysis only, with exact Poisson intervals.
- **"100 % ISO/TS 15066 compliance".** Replaced by a clause-level assessment that
  states, for each requirement, what was assessed in simulation and what was not
  assessed at all. No SIL and no Performance Level is claimed.

### Added

- `analysis/ablation.py` and `cfg/ablation_A{0..3}.yaml`: architectural ablation
  isolating the contribution of the architecture from that of the control
  algorithm. The architecture costs ~0.3 ms of median cycle time; it does not
  make the loop faster.
- `analysis/check_against_paper.py`: fourteen headline quantities recomputed and
  asserted against the printed values; wired into CI.
- `config/seeds.json`, `docs/REPRODUCE.md`, `data/schemas/`, `sbom/sbom.spdx.json`.

### Changed

- `analysis/paired_stats.py`: the unit of analysis is now the 20-minute segment
  mean, paired by segment (n = 30), not the individual control cycle. Holm
  replaces Bonferroni over twelve pre-specified hypotheses. Two of the six
  baseline comparisons no longer reach significance.
- The barrier network was retrained for the 66-dimensional input and revalidated;
  the reported accuracy is that of the adapted model.
- `figures/p2_figures.py`: Figure 10 rebuilt (Weibull probability plot, bootstrap
  CI on the shape, KS statistic, exact Poisson intervals); Figure 6b now shows the
  serial critical path rather than a sum that included a concurrent stage; every
  panel labelled measured / simulated / estimated / projected.
