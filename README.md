# hrc-architecture 3.1

A hardware-abstracted control architecture for human–robot collaboration with a
barrier-function safety filter. It has three layers:

* a hardware-abstraction layer: a Universal Robots RTDE adapter, tested against the vendor's
  URSim controller, and KUKA FRI and ABB EGM adapters, which compile but were not evaluated;
* a control layer: a 20 ms control loop with one quadratic program that imposes the
  supervisor's speed limits, an ISO/TS 15066 speed-and-separation limit, an optional learned
  barrier that abstains near the separation floor, and geometric barriers tightened for the
  measured age and the calibrated position error of the human-state estimate; every dispatched
  command is checked against all constraints and replaced by a stop if it fails;
* an integration layer: Modbus TCP and REST. OPC UA is optional and was not built in the
  evaluated binary.

This is the software evaluated in revision 4 of manuscript electronics-4587969 (MDPI
*Electronics*). Release 3.1 corrects three defects of release 3.0 found in review (speed scaling
applied after the QP, the supervisor's handling of simultaneous conditions, and a data race in
the sequence-lock slot); `docs/CHANGES_3.1.md` lists every change.

**This software must not be connected to a robot that can reach a person.** It has not been
assessed against IEC 61508, ISO 13849, ISO 10218 or ISO/TS 15066, and the stop it issues is not
a safety-rated function.

## Pre-registration and frozen states

| Tag | What it fixes |
|---|---|
| `r31-calibration` | Code, written pre-registration (`docs/PREREGISTRATION_3.1.md`: calibration rule, campaign design, hypotheses, tuning rule, analysis) and analysis scripts, published before the first run. |
| `campaign-v4` | Configuration produced by the calibration rule, and every campaign configuration except the comparison. |
| `campaign-v4-compare` | Comparison configurations, generated from the tuning runs by the rule fixed at `r31-calibration`. |
| `campaign-v4-report` | Commit used to compute `results.json`. |

The records of their identifiers, committed through the GitHub interface at the time of each
publication, are in `docs/freeze/` on the main branch. The scripts that turn `results.json`
into the numbers, tables and figures of the manuscript are in `paper/r4_reproduction/` (with a
README giving the route and the commands); those of the round-3 manuscript are in
`paper/r3_reproduction/`.

The raw run records of release 3.1, the campaign executables and `results.json` are deposited
at Figshare, DOI [10.6084/m9.figshare.35081113](https://doi.org/10.6084/m9.figshare.35081113).
The records of release 3.0 remain at DOI
[10.6084/m9.figshare.34845711](https://doi.org/10.6084/m9.figshare.34845711) (tags `campaign-v3`,
`campaign-v3-compare`, `campaign-v3-report`, unchanged).

## Provenance

Releases 1.0.0–2.1.0 of this repository did not contain experimental records; release 3.x is a
re-implementation, and every result it reports comes from raw, hash-manifested run directories
written by the programs below. `docs/PROVENANCE_NOTICE.md` and `docs/DATA_POLICY.md` give the
details. The history of the repository is kept unchanged so that it remains auditable.

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
docs/             RUNBOOK, BUILD, PREREGISTRATION_3.1, CHANGES_3.1, DATA_POLICY, PROVENANCE_NOTICE
paper/           r3_reproduction/, r4_reproduction/ (scripts of the manuscript)
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

`docs/RUNBOOK.md` gives the procedure and `docs/BUILD.md` the build commands: training, URSim conformance, the campaigns
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
