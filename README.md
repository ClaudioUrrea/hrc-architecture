# hrc-architecture 3.x

Vendor-neutral embedded control architecture for human–robot collaboration: hardware
abstraction (Universal Robots RTDE, KUKA FRI, ABB EGM/RWS), a bounded-latency control layer
with geometric and learned control barrier functions, a safety supervisor, and an integration
layer (Modbus TCP, REST, OPC-UA).

> **Read first — provenance.** Release 3.x is a re-implementation. The code and the original
> records of the study reported in manuscript electronics-4587969 (MDPI *Electronics*) were
> lost, and the data files deposited with releases 1.0.0–2.1.0 were generated from the
> manuscript's own summary statistics; they are not experimental records
> (`docs/PROVENANCE_NOTICE.md`). Release 3.x contains no data generated that way. Every
> result is to be produced by the programs below, which write raw, hash-manifested run
> directories (`docs/DATA_POLICY.md`).

**This software must not be connected to a robot that can reach a person.** It has not been
assessed against IEC 61508, ISO 13849, ISO 10218 or ISO/TS 15066, and the emergency stop it
issues is not a safety-rated function.

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
docs/             RUNBOOK, DATA_POLICY, DESIGN_DECISIONS, REVIEWER2_R3_MAP, PROVENANCE_NOTICE
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

## Reproducing the paper

`docs/RUNBOOK.md`: real-time host set-up, pilot and freeze, training, URSim conformance, the
campaigns (`tools/make_campaigns.py`, `tools/run_campaign.py`), PLC and effort timing
(`tools/worklog.py`), and `analysis/report.py`, which writes `results/results.json` with the
run directories (and their manifest hashes) behind every number.

## License

MIT (code). Data deposited from runs: CC BY 4.0.
