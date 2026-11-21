# Raw records of the release-3.1 evaluation (hrc-architecture, campaigns v4)

Data deposit of revision 4 of manuscript electronics-4587969 (MDPI *Electronics*), *A
Hardware-Abstracted Control Architecture with a Barrier-Function Safety Filter for Human–Robot
Collaboration: Publicly Pre-Registered Simulation Evaluation of Timing, Fault Handling and Safety
Behaviour*, by Claudio Urrea (University of Santiago of Chile). Licence: CC BY 4.0, except the third-party documents in `vendor_documents_UR.tar.gz`.

Everything here was produced by running the software; no file was generated, edited or filtered by
hand. All results are **simulated** (kinematic UR5e model, scripted operator, camera model) on a
general-purpose, non-real-time Linux host; no physical robot or person was involved.

## Code and pre-registration

Code: <https://github.com/ClaudioUrrea/hrc-architecture>, branch `release-3.1`. The pre-registration
and the code were published with tag `r31-calibration`; the configuration frozen after the calibration
with `campaign-v4`; the comparison configurations with `campaign-v4-compare`; the commit that computed
the results with `campaign-v4-report`. The records of their identifiers, with GitHub server time
stamps, are in `docs/freeze/` on the main branch and in `freeze_records.tar.gz`.
`source_campaign-v4-report.tar` is byte for byte the archive whose SHA-256 was published in
`FREEZE_campaign-v4-report.md`.

## Files

| File | Content |
|---|---|
| `runs_<experiment>.tar.gz` | Closed run directories of each campaign, as listed in `INDEX.csv` (calibration, ablation, fault injection, fault sensitivity, tuning, comparison, timing, protocol). |
| `runs_other_closed.tar.gz` | Closed directories not written by the run logger (code metrics, protocol benchmark output). |
| `runs_interrupted_excluded.tar.gz` | The seven runs interrupted during the campaigns and run again; excluded from every analysis (`NOTE_interrupted_runs.md`). |
| `conformance_release31_additional.tar.gz` | URSim conformance test repeated with release 3.1 after the campaigns (not pre-registered). |
| `not_a_run_mistaken_conformance_start.tar.gz` | Directory written by a mistaken start of the conformance program without a controller, after the report; not a run, not used (note inside). |
| `runs_pilot_not_used.tar.gz` | The four pilot run directories that were kept (3 November 2026, before the pre-registration was published); not used for any result. Earlier pilot runs were made in temporary directories and were not kept. |
| `host_system_event_log_extract.txt` | Extract of the Windows System event log of the host, 3–21 November 2026: unexpected restarts (Kernel-Power 41, 6008, bug checks), Windows Update events and power-plan changes (manuscript, Section 5.1). Messages are in Spanish, as written by the host. |
| `INDEX.csv`, `INVENTORY.csv` | Run index written by the logger; inventory mapping every directory to its archive and manifest hash. |
| `queue4.log`, `watchdog_launches.log` | Log of the campaign queue and launches by its watchdog (chronology, incidents). |
| `results.json`, `tuning_selection.json`, `SHA256SUMS_results` | Output of `analysis/report.py` at `campaign-v4-report` (pre-registered analysis). |
| `stop_samples_compare.csv`, `stop_check_compare.csv`, `stop_check_summary.txt` | Stopping check (`tools/stop_samples.py`, `tools/stop_check`). |
| `results_extra.json`, `results_supp.json`, `timing_miss_detail.json` | Supplementary analyses (`paper/r4_reproduction/`: `extra_analysis.py`, `supp_r4.py`, `timing_miss_detail.py`), specified after the campaigns. |
| `manuscript_macros_r4_numbers.tex` | Every number printed in the manuscript, as generated from the files above. |
| `executables_campaign.tar.gz`, `executables_SHA256SUMS` | Campaign executables built at `campaign-v4` (`hrc_run` SHA-256 3364796a…64573b). The six calibration runs, which precede that tag, used the executable built at `r31-calibration` (rebuildable from `source_r31-calibration.tar.gz`; its commit label is in each calibration manifest). |
| `source_campaign-v4-report.tar`, `source_r31-calibration.tar.gz`, `git_tags.txt`, `git_log.txt` | Source at the report and pre-registration tags. |
| `vendor_documents_UR.tar.gz` | Copies of the Universal Robots documents used by the conformance test, with their SHA-256 (retrieved 5 November 2026). These are third-party documents, deposited only so that the conformance checks can be verified; they remain the property of Universal Robots and are **not** covered by the CC BY 4.0 licence of this item. |
| `freeze_records.tar.gz` | Pre-registration and freeze records with their published hashes. |
| `MANIFEST_DEPOSIT.sha256` | SHA-256 of every file of this deposit. |

## Run directories

Each run directory holds `config.json` (configuration actually used), `manifest.json` (host, kernel,
real-time settings obtained, build label, start and end, status, record counts), `schema.json`,
`cycles.bin` (one binary record per 20 ms control cycle), `events.jsonl` (time-stamped events),
`injection_schedule.csv` (written before the first cycle) and `MANIFEST.sha256`. The readers in
`analysis/hrc_logs.py` verify `MANIFEST.sha256` before reading a run. To recompute every reported
number: unpack the archives into one `runs/` folder and follow `paper/r4_reproduction/README.md`.

The records of release 3.0 (previous version of the manuscript) are in Figshare item
10.6084/m9.figshare.34845711 and are not repeated here.
