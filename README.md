> [!WARNING]
> **Correction of data provenance (12 October 2026).** The data files in releases 1.0.0 to 2.1.0
> of this repository and of the Figshare deposit [doi:10.6084/m9.figshare.33194013](https://doi.org/10.6084/m9.figshare.33194013)
> are **not experimental records**. The original logs and the implementation source code of the study
> described in manuscript electronics-4587969 (MDPI *Electronics*) were lost, and no backup exists.
> The deposited datasets – including those previously described as "recorded values"
> (`faults_450.csv`, `interfailure.csv`, `plc_runs.csv`, `effort_log.csv`, `conformance_log.csv`,
> `cloc_lizard.json`) and the files described as "reference reconstructions" – were reconstructed
> from the summary statistics printed in the manuscript. They cannot be
> used to verify that manuscript and must not be used as evidence for its results. The analysis
> scripts in those releases recompute the printed numbers from the reconstructed files; this shows
> internal consistency only. These releases also did not contain the C++ implementation described in
> the manuscript's Data Availability Statement.
>
> The author has informed the journal. The implementation is being rebuilt (release 3.x) and the
> experiments are being repeated with raw logs written by the software, with SHA-256 manifests. The
> source code and analysis scripts of the re-implementation are written with the assistance of an AI
> coding assistant (Claude, Anthropic) from the author's specifications; the author defined the
> architecture and the experimental design, reviews and tests the code, and is fully responsible for
> it. The AI generates no data: all results come from running the software. Any
> future publication will report only results from those new runs. The history of this repository is
> kept unchanged so that it remains auditable.

# hrc-architecture

> **Data provenance.** See the correction notice at the top of this page: none of the deposited data files is an experimental record; all of them, including those previously described as recorded values, were reconstructed from the summary statistics reported in the paper.

Reference implementation and reproducibility package for

> C. Urrea, *Vendor-Neutral Embedded Control Architecture for Safety-Critical Human–Robot
> Collaboration: Hardware Abstraction, Bounded-Latency Execution and Industrial Protocol
> Integration Evaluated Against Simulated Vendor Interfaces*, **Electronics** (under review),
> manuscript `electronics-4587969`.

A three-layer embedded control architecture for collaborative robot cells. A hardware
abstraction layer places URScript/RTDE, KUKA FRI and ABB Robot Web Services behind one set of
interfaces; a real-time control layer runs a Lipschitz-constrained neural control barrier
function under TensorRT inside a 20 ms budget; an integration layer publishes an IEC 62541
OPC-UA server, a Modbus TCP gateway and an EtherCAT master.

## Read this first

**Every number in the paper was produced by this software executing against *simulated* robot,
sensor and PLC interfaces.** No physical manipulator, no safety-rated hardware, no industrial
network and no human participant was involved at any stage. Nothing here has been assessed
against IEC 61508, ISO 13849, ISO 10218 or ISO/TS 15066, no Safety Integrity Level or
Performance Level is claimed, and **this code must not be deployed on a robot that can reach a
person**. Sections 3.1 and 3.4 and Tables 3 and 4 of the paper classify every reported quantity as measured,
simulated, estimated or projected, and state what limits its transferability.

## Layout

```
cfg/          run configurations, one per reported experiment
config/       seeds.json — master seed and every derived per-scenario seed
analysis/     one script per figure or table in the paper
train/        CBF training and evaluation
data/         deposited measurements (see data/README.md for schemas)
api/          OpenAPI 3.0 specification of the REST layer
sbom/         SPDX software bill of materials
docs/         REPRODUCE.md — end-to-end instructions
tests/        conformance/ — clause-by-clause vendor-interface checklists and logs
figures/      p2_figures.py — regenerates all thirteen figures
              ga_p2_electronics.py — regenerates the graphical abstract
```

## Reproducing the paper

```bash
docker build -t hrc-arch .
docker run --rm -v "$PWD/out:/work/out" hrc-arch make all
```

or, natively:

```bash
python -m pip install -r requirements.txt
make all
```

`make all` runs every script in `analysis/`, writes the numbers quoted in the paper to
`out/results.json`, and regenerates the thirteen figures into `out/figures/`. `make check`
asserts that each recomputed value matches the value printed in the paper; it exits non-zero
if any disagrees. Table 6 of the paper maps each result to the configuration, script and data
file that produce it, and `docs/REPRODUCE.md` repeats that mapping here.

## What this release withdrew

Release 2.1.0 accompanies the revised manuscript (major revision, round 1). The withdrawals below took effect at 2.0.0 and remain in force. Three claims present in 1.x are **withdrawn**,
and `make check` now asserts that they stay withdrawn:

- the per-cycle deadline-miss bound of 8.3 × 10⁻⁸ — it treated 3.6 × 10⁷ dependent cycles as
  independent trials; the bound is now stated only at the block grain (no miss in 120
  cold-started 100-minute blocks, so 3/120 = 2.5 × 10⁻²);
- the claim that the layering improves the latency tail — the monolithic baseline holds the
  lowest observed maximum of the seven ablation configurations;
- the cycle-time advantage over distributed MPC and over a single-objective barrier controller
  — it does not survive giving those baselines a matched tuning budget.

Two published quantities were also corrected: the ablation's dispersion column (0.15 ms was
release jitter, not execution-time spread, which is 1.71 ms) and the availability figure, which
no longer borrows the injection campaign's recovery mean. `CHANGELOG.md` records each against
the version in which it took effect.

## What is *not* in this repository

- Vendor software development kits. URScript/RTDE, KUKA Sunrise/FRI and ABB RWS/EGM must be
  obtained from the manufacturers under their own licence terms; the adapters build against
  them but do not redistribute them.
- The vendor simulators (URSim, Sunrise.OS, RobotStudio, PLCSIM Advanced, Studio 5000 Logix
  Emulate, GX Simulator3) and CoppeliaSim, for the same reason.
- The two largest telemetry files (`cycles_36M.parquet`, `ablation_cycles.parquet`). They are
  in the Figshare deposit, DOI [10.6084/m9.figshare.33194013](https://doi.org/10.6084/m9.figshare.33194013);
  `make fetch-data` downloads them.

## Licence

Code: MIT (`LICENSE`). Data and figures: CC BY 4.0 (`LICENSE-DATA`). See `CITATION.cff` for how
to cite.
