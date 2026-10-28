# hrc-architecture 3.x

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

> [!WARNING]
> **Correction of data provenance (12 October 2026).** The data files in releases 1.0.0 to 2.1.0
> of this repository and of the Figshare deposit [doi:10.6084/m9.figshare.33194013](https://doi.org/10.6084/m9.figshare.33194013)
> are **not experimental records**. The original logs and the implementation source code of the
> study described in earlier versions of manuscript electronics-4587969 were lost, and no backup
> exists. The files deposited with those releases were reconstructed from the summary statistics
> printed in the manuscript, so they cannot verify it (`docs/PROVENANCE_NOTICE.md`). Release 3.x
> is a re-implementation and contains no data generated that way. Every result reported in the
> revised manuscript comes from raw, hash-manifested run directories written by the programs
> below (`docs/DATA_POLICY.md`). The history of this repository is kept unchanged so that it
> remains auditable; releases 1.0.0–2.1.0 remain under tag `v2.1.0`.

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

## License

MIT (code). Data deposited from runs: CC BY 4.0.
