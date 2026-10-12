# Data policy

This repository exists because the original records of the study were lost and the data
deposited with revisions R1–R2 of manuscript electronics-4587969 were synthetic
reconstructions generated from the paper's own summary statistics. That deposit cannot verify
anything. The rules below make sure it cannot happen again.

## 1. Only instruments write data

* Every number in the paper comes from a run directory written by a program in this
  repository while it was executing (`hrc_run`, `hrc_conformance`, `hrc_protocol_bench`,
  `train/train_cbf.py`) or from a chained work log (`tools/worklog.py`).
* **No file in a run directory is ever edited, regenerated, resampled, filtered or
  "cleaned" after the run closes.** The logger makes the files read-only and records their
  SHA-256 in `MANIFEST.sha256`; `analysis/hrc_logs.py` refuses any run whose hashes do not
  match.
* There is no tool in this repository that produces data from target statistics, and none
  may be added. The analysis scripts never read a number from the manuscript.

## 2. Nothing is discarded silently

* Runs that crash keep status `running`/`incomplete`/`interrupted` in `manifest.json` and are
  listed in `runs/INDEX.csv`. The analysis skips them **and reports that it did**.
* Runs in which the requested real-time policy could not be applied (`rt_applied.policy_ok =
  false`) are excluded from timing results and listed as excluded.
* Cycles carrying an injected overrun are counted and reported separately (total, excluded,
  retained), never dropped.
* If a run is repeated, both runs stay in `runs/`; the paper states which one is used and why.

## 3. Three copies, verified

* Every run is mirrored at close to every `--backup` directory and verified hash by hash.
  `tools/run_campaign.py` refuses to start without a backup and stops if verification fails.
* Recommended: one external disk + one cloud-synchronised folder, plus a weekly archive
  (`tar` of `runs/` with its SHA-256) uploaded to Figshare as a *private* item while the
  campaign runs.
* The source tree is under git; push to GitHub after every change. Each run manifest records
  the commit it was built from (a `-dirty` suffix means uncommitted changes: do not use such
  runs for the paper).

## 4. Pre-registration

Before the first campaign run: freeze `cfg/base_sim_ur5e.json`, generate the campaign
configurations with `tools/make_campaigns.py`, commit them, and tag the commit
(`git tag campaign-v3`). Scenario geometry, fault rates, tuning grids and the tuning
selection rule are fixed by that commit. A pilot run before freezing is fine and expected; its
runs are kept in a separate `runs_pilot/` directory and never used for the paper.

## 5. Reporting

* Every quantity in the paper is produced by `analysis/report.py`, which writes
  `results/results.json` with the list of run directories and the hash of each
  `MANIFEST.sha256` used.
* Results are reported whatever they are. If a result is worse than the earlier manuscript
  stated, the paper says so.
* The deposit (Figshare/GitHub) contains the raw run directories, the configurations, the
  exact source commit and `results.json`. Synthetic files from earlier versions are not
  included in the new deposit; the old versions stay retrievable under their own DOIs with a
  corrected description (see `docs/PROVENANCE_NOTICE.md`).
