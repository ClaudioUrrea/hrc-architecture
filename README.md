# hrc-architecture

Reference implementation and reproducibility package for

> C. Urrea, *Vendor-Neutral Embedded Control Architecture for Safety-Critical Human–Robot
> Collaboration: Hardware Abstraction, Bounded-Latency Execution and Industrial Protocol
> Integration Evaluated Against Simulated Vendor Interfaces*, **Electronics** (under review),
> manuscript `electronics-4535423`.

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
person**. Section 3.1 and Table 3 of the paper classify every reported quantity as measured,
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
figures/      p2_figures.py — regenerates all twelve figures
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
`out/results.json`, and regenerates the twelve figures into `out/figures/`. `make check`
asserts that each recomputed value matches the value printed in the paper; it exits non-zero
if any disagrees. Table 4 of the paper maps each result to the configuration, script and data
file that produce it, and `docs/REPRODUCE.md` repeats that mapping here.

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
