# hrc-architecture 3.x

> **Version evaluated in the published article: release 3.1, on branch [`release-3.1`](https://github.com/ClaudioUrrea/hrc-architecture/tree/release-3.1).**
>
> Urrea, C. A Hardware-Abstracted Control Architecture with a Barrier-Function Safety Filter for Human–Robot Collaboration: Publicly Pre-Registered Simulation Evaluation of Timing, Fault Handling and Safety Behaviour. *Electronics* (MDPI), 2026. Manuscript electronics-4587969, accepted on 23 November 2026; the DOI of the article will be added here on publication.
>
> | Tag | Commit | What it fixes |
> |---|---|---|
> | [`r31-calibration`](https://github.com/ClaudioUrrea/hrc-architecture/tree/r31-calibration) | `1511fd5` | Code, written pre-registration (`docs/PREREGISTRATION_3.1.md`), calibration rule, campaign generator and analysis, published before the first run |
> | [`campaign-v4`](https://github.com/ClaudioUrrea/hrc-architecture/tree/campaign-v4) | `f5cb16b` | Configuration of every campaign, frozen after the calibration runs |
> | [`campaign-v4-compare`](https://github.com/ClaudioUrrea/hrc-architecture/tree/campaign-v4-compare) | `ab88b07` | Comparison configurations, generated from the tuning runs by the fixed rule |
> | [`campaign-v4-report`](https://github.com/ClaudioUrrea/hrc-architecture/tree/campaign-v4-report) | `ab88b07` | Commit that computed `results.json` (the same commit as `campaign-v4-compare`) |
>
> The records of these identifiers, committed with GitHub server time stamps, are in [`docs/freeze/`](docs/freeze) on this branch. Build instructions (`docs/BUILD.md`), the list of changes from release 3.0 (`docs/CHANGES_3.1.md`) and the scripts that turn `results.json` into the numbers, tables and figures of the article (`paper/r4_reproduction/`) are on branch `release-3.1`. The raw, hash-manifested records of every release-3.1 run are deposited at Figshare, DOI [10.6084/m9.figshare.35081113](https://doi.org/10.6084/m9.figshare.35081113) (CC BY 4.0).
>
> **The rest of this page describes release 3.0** (revision 3 of the manuscript, tags `campaign-v3*`). Its records remain deposited unchanged (DOI [10.6084/m9.figshare.34845711](https://doi.org/10.6084/m9.figshare.34845711)); its results are superseded by those of release 3.1.

A hardware-abstracted control architecture for human–robot collaboration with a
barrier-function safety filter. It has three layers:

* a hardware-abstraction layer: a Universal Robots RTDE adapter, tested against the vendor's
  URSim controller, and KUKA FRI and ABB EGM adapters, which compile but were not evaluated;
* a control layer: a 20 ms control loop with a CBF quadratic program that combines geometric
  constraints tightened for the measured age of the human-state estimate, an optional learned
  barrier that abstains near the separation floor, an ISO/TS 15066 speed-and-separation limit,
  and one supervisor with a single priority order;
* an integration layer: Modbus TCP and REST. OPC-UA is optional and was not built in the
  evaluated binary.

This is the software evaluated in revision 3 of manuscript electronics-4587969 (MDPI
*Electronics*), *A Hardware-Abstracted Control Architecture with a Barrier-Function Safety
Filter for Human–Robot Collaboration: Pre-Registered Evaluation of Timing, Fault Handling and
Interface Conformance*.

**This software must not be connected to a robot that can reach a person.** It has not been
assessed against IEC 61508, ISO 13849, ISO 10218 or ISO/TS 15066, and the emergency stop it
issues is not a safety-rated function.

## Frozen states

| Tag | Commit | What it fixes |
|---|---|---|
| `campaign-v3` | `1a51a57` | Design, trained barrier model and every campaign configuration, frozen before the first campaign run. Its identifiers are published in `PREREGISTRATION.md`. |
| `campaign-v3-compare` | `80b8f72` | Comparison configurations, generated from the tuning runs by the rule frozen at `campaign-v3`. |
| `campaign-v3-report` | `a2ea7bc` | Commit that generated `results.json` (a formatting-only fix of `tools/paper_numbers.py`). |

Branch `release-3.x` ends at `campaign-v3-report`. The raw run records, the campaign executables
and `results.json` are deposited at Figshare, DOI [10.6084/m9.figshare.34845711](https://doi.org/10.6084/m9.figshare.34845711).

## Layout

```
include/hrc/      interfaces (contracts), types, safety, supervisor, adapters, logging
src/              implementation: safety/, control/, adapters/, sim/, integration/, faults/, log/
apps/             hrc_run (experiments), hrc_conformance, hrc_protocol_bench, hrc_infer_server
tests/            test_safety_isolated (links no vendor/sim/protocol code), test_system
train/            barrier-network training (NumPy)
cfg/              base configuration, robot DH files, fault-rate rationale, generated campaigns
tools/            make_campaigns.py, run_campaign.py, worklog.py, code_metrics.sh
analysis/         readers that verify hashes, and one script per reported result; report.py
docs/             RUNBOOK, DATA_POLICY, PROVENANCE_NOTICE
```

## Build

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j
cd build && ctest --output-on-failure
```
C++17, no third-party dependency for the core. Optional: KUKA FRI SDK, ABB `egm.proto`
(protobuf), open62541.

## One run

```bash
python3 train/train_cbf.py --run-root runs              # trains and exports the barrier
cp runs/*_cbf_train/model.json models/cbf_ur5e.json
./build/hrc_run --config cfg/base_sim_ur5e.json --duration 60 --backup /path/to/backup
```
A run directory contains `config.json`, `manifest.json` (host, kernel, RT settings actually
applied, build commit), `schema.json`, `cycles.bin` (one 192-byte record per control cycle),
`events.jsonl`, `injection_schedule.csv` and `MANIFEST.sha256`. It is made read-only at close
and mirrored to every backup directory with hash verification.

## Reproducing the results

`docs/RUNBOOK.md` gives the procedure: training, URSim conformance, the campaigns
(`tools/make_campaigns.py`, `tools/run_campaign.py`) and `analysis/report.py`, which writes
`results/results.json` with the run directories (and their manifest hashes) behind every number.
Its first section states how the campaigns of the article were actually executed. To recompute
the reported numbers without running anything, unpack the deposited run directories and run
`analysis/report.py` on them.

## Development

The source code of release 3.x and its analysis scripts were written with Claude (Anthropic)
from the author's specifications; the author defined the architecture and the experimental
design, and reviewed and tested the code. The figures of releases 1.0.0–2.1.0 were also prepared
with this tool, following the author's instructions. No data were generated with it: every
result comes from running the software. Co-Authored-By trailers in the commit history are added
automatically by the coding tool; they record the tool's assistance, declared in the article,
and do not denote authorship.

## Earlier releases

Releases 1.0.0–2.1.0 (tag `v2.1.0`) are superseded and are not evidence for any manuscript: their data files were reconstructed from published summary statistics, not recorded (`docs/PROVENANCE_NOTICE.md`).

## License

MIT (code). Data deposited from runs: CC BY 4.0.
