# Changelog

## 1.0.0 — 2026-09-09

Release accompanying the revised manuscript `electronics-4535423` (R1).

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
