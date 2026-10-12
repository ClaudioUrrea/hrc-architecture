# Reviewer 2, round 3: what answers each point

Status legend: **D** = answered by new raw data (campaign named); **C** = answered by the code
and its documentation; **T** = text correction in the manuscript only.

| # | Reviewer point | Answer | Status |
|---|---|---|---|
| 1 | Original records; separate synthetic data; which results remain verifiable; re-run experiments | Originals lost; disclosed to the editor. All experiments re-run with this code; raw run directories with SHA-256 manifests deposited; no synthetic files in the new deposit; earlier deposit relabelled (`docs/PROVENANCE_NOTICE.md`) | D (all campaigns) |
| 1b | "Corrected execution-time SD recomputed from the deposited traces" | Withdrawn: those traces were generated. New SD computed from raw cycle logs (`analysis/timing.py`, `ablation.py`) | D |
| 2 | Which components came from vendors, which written by the author, which behaviours were added by wrappers/fault injection | URSim / Sunrise / RobotStudio / PLC simulators = vendor software, unmodified. Adapters, follow script, built-in robot/human/camera simulator, fusion, fault injector = author. Faults are injected only through `src/faults` hooks into the built-in simulator and the camera model; with URSim, only host-side faults are injected. Conformance items test the adapter against the vendor simulator, not against a model written by the author (`apps/hrc_conformance.cpp`) | C + T |
| 3 | Host ↔ Jetson: protocol, what the 0.29 ms includes | UDP request/reply of fixed size; cycle log separates client wall time from server compute (`d_learned_ns`, `d_remote_compute_ns`); no GPU code, so pinned/unified memory statements are removed | C + D (remote-inference variant) |
| 4 | 20 Hz watchdog vs 100–105 ms | Stream freshness checked every 20 ms cycle; detection latency measured from injection to detection in the event log; formula removed | C + D (injection) |
| 5 | Protective stop vs reduced-speed: priority | Single priority table (`include/hrc/supervisor.hpp`, `docs/DESIGN_DECISIONS.md`): one stream lost → reduced speed; estimate lost → protective stop | C + T |
| 6 | 0.093 m stopping distance impossible | Constant-deceleration model: `S_s = v²/(2a)` ≤ `v·T_s`; separation distance recomputed every cycle with measured data age; stop durations measured in logs | C + T |
| 7 | 1.5 s ramp vs 0.25 s stop time: link to operating states | One deceleration parameter per space (joint 3.0 rad/s², Cartesian 1.2 m/s²); the stop duration follows from speed; measured | C + D |
| 8 | Injected overruns excluded but abstract says zero misses | `analysis/timing.py` reports total / injected-excluded / retained cycles and misses in each; the abstract will quote the same definition | D + T |
| 9 | What the block-level bound covers | One block = one cold-started run; bound applies to retained cycles of nominal operation under the stated load profile; exact bound `1 − 0.05^(1/n)` | D + T |
| 10 | Sources of fault rates; clustered / other arrivals | Rates are design parameters, no external source claimed (`cfg/fault_rates.md`); sensitivity campaign with clustered and Weibull arrivals at 0.5/1/1.5× | D (sensitivity) + T |
| 11 | Constraint violations need operator clearance but reliability counts only partitions | One classification: operator-intervention = network partition + constraint violation + memory allocation (`analysis/faults.py`) | C + T |
| 12 | Interval from campaign start to first failure | Each run starts cold, so its first interval is a complete interval; each run's last interval is censored | C + T |
| 13 | Original fault-event timings for downtime | Downtime measured from the 50 Hz cycle log (time in stopped modes), events with timestamps in `events.jsonl` | D |
| 14 | Effort as "potentially optimistic", not a lower bound | Text change; effort re-measured with the chained work log | T + D (worklog) |
| 15 | Appendix C: narrowing 160–250 h to 200–250 h raises the estimated/measured ratio | Correct: removing low values of the denominator-free estimate *increases* the ratio. Text corrected (or the estimate dropped) | T |
| 16 | Figure 12a mixes percentages, LOC and a time ratio on one axis | Split into separate indicator panels with their own units | T (figure) |
| 17 | Exact revisions of vendor manuals; version-specific archive with original evidence | Cite document numbers/versions actually used in the new runs (URSim version is logged by the conformance tool); deposit a new version containing only the new raw evidence | D + T |
