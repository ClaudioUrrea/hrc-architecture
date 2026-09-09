# Deposited data

All files are outputs of the software running against simulated interfaces. See
`schemas/` for the JSON Schema of each file and `../docs/REPRODUCE.md` for the
script that consumes it.

| File | Rows | Description |
|---|---|---|
| `plc_runs.csv` | 12 | Per-run commissioning times, three toolchains, with the per-step decomposition |
| `effort_log.csv` | 10 | Task-level porting hours with the counted/not-counted flag of Appendix C |
| `faults_450.csv` | 166 | Fault events over the 200 h campaign: category, time, detection, recovery, population flags |
| `interfailure.csv` | 156 | Service-affecting inter-failure intervals entering the Weibull fit |
| `cloc_lizard.json` | — | Line counts and cyclomatic complexity per module |
| `cycles_36M.parquet` | 3.6e7 | Control-cycle telemetry (Figshare only, ~410 MB) |
| `protocol_samples.parquet` | 1.2e5 | Protocol transaction latencies (Figshare only) |
| `ablation_cycles.parquet` | 4.0e4 | Per-cycle timing for A0–A3 (Figshare only) |
| `segments_30.parquet` | 210 | Segment means, seven methods x 30 segments (Figshare only) |
| `cbf_dataset_66d.npz` | 5.0e4 | Barrier training set, 66-dimensional input (Figshare only) |

## Population definitions

Fixed in Section 8.3 of the paper **before** the analysis and not adjusted
afterwards. `all_faults` = 166. `service_affecting` = 156; the ten configuration
inconsistencies are excluded because they are rejected before application and
consume no production time. `operator_intervention` = 6, the network-partition
events. No transient-duration filter is applied: such a filter would be a
post-hoc choice made after seeing the intervals.

## Censoring

The run terminates at 200 h, so the final interval of the sequence is
right-censored and is dropped from the Weibull likelihood. The exact Poisson
intervals use the full 200 h exposure and are unaffected.
