# What this implementation does, and where it differs from the R2 manuscript

The R2 manuscript described a system whose code and records are lost. This rebuild implements
the same architecture, but several mechanisms are specified differently, mostly because the
reviewer's round-3 questions showed that the old description was ambiguous or physically
inconsistent. **The paper must describe what this code does**, so every item below is a text
change the manuscript needs once the new results exist.

## Architecture and contracts

| Item | R2 manuscript | This implementation |
|---|---|---|
| `IRobotController` | 12 methods incl. `moveCartesian` | 13 methods; cyclic path is `getCurrentState`, `streamJointVelocity`, `setOverride`, `protectiveStop`, `emergencyStop`, `getHealthStatus`; `moveCartesian` dropped (no consumer) |
| Isolation claim | safety module compiles without vendor libraries | enforced by the build: `test_safety_isolated` links `hrc_safety` + `hrc_core` only |
| Code reuse / LOC | 9,274 shared, 456–523 per adapter | must be re-counted with `cloc` on this tree (`tools/code_metrics.sh`); numbers will differ |

## Control and safety

| Item | R2 manuscript | This implementation |
|---|---|---|
| Controller | MPC, horizon 10, 60 variables, qpOASES | nominal joint-space controller + one-step CBF-QP safety filter (6–7 variables), solved exactly by a Goldfarb–Idnani active-set method (`src/safety/geometric_cbf.cpp`) |
| QP infeasibility | slack on learned constraint, retry, fallback | learned rows dropped and QP re-solved with geometric rows only (flag `qp_relaxed`, mode GEOMETRIC_FALLBACK for 5 s); if still infeasible: protective stop that cycle (flag `qp_failed`) |
| Learned barrier | classifier, 97.2 % accuracy, PyTorch, TensorRT on Jetson | regression of clearance `clip(d_min − 0.15, −0.3, 1.0)` m with asymmetric loss; NumPy training; C++ CPU inference, optional remote server on any device (`hrc_infer_server`) |
| Learned-barrier gray zone | clamp `min(h, 0)` | the model abstains for that cycle (`|h| < 0.15`); geometric rows govern |
| Human motion term | assumed bound 2.0 m/s | configurable: fixed design bound (default 1.0 m/s), measured + margin, or worst case 2.0 m/s; the same bound sizes the data-age term |
| Data age | fusion latency + one period (max 26.9 ms) | measured per cycle from the **acquisition** time of the oldest contributing camera frame (includes camera latency); logged in every cycle |
| Constraint violation | `h(x) < −0.05` | measured separation below the active floor by more than 0.05 m |

## Supervisor: one priority order (reviewer: "which rule takes priority")

`include/hrc/supervisor.hpp` holds the table. The most severe active condition decides the
mode; there is no other path to a mode change.

| Severity | Mode | Speed scale | Entered when |
|---|---|---|---|
| 0 | NOMINAL | 1.0 | — |
| 1 | LOW_CONFIDENCE | 0.7, floor 225 mm | 0.4 ≤ mean confidence < 0.6 |
| 2 | DEGRADED_STREAM | 0.5 | ≥1 camera silent > 100 ms, estimate still available |
| 3 | GEOMETRIC_FALLBACK | 0.5, floor 300 mm | learned barrier failed / QP relaxed |
| 4 | OVERRUN_SHED | 1.0 | previous cycle missed its deadline |
| 5 | PROTECTIVE_STOP (auto-resume) | 0 | no camera alive, estimate older than 150 ms, or confidence < 0.4; 3 consecutive comm errors; 5 consecutive overruns; watchdog stop |
| 6 | PROTECTIVE_STOP_LATCHED (operator) | 0 | network partition (no robot state > 150 ms); constraint violation |
| 7 | EMERGENCY_STOP (operator) | 0 | memory allocation failure |

So: a sensor timeout of **one stream** gives reduced-speed operation; loss of the
**estimate** (all streams, stale, or low confidence) gives a protective stop. Both statements
of the R2 text become true, each for its own condition.

## Stopping (reviewer: 0.093 m vs 0.075 m; 1.5 s ramp vs 0.25 s)

* One stopping model everywhere: constant deceleration. `T_s = v/a`, `S_s = v²/(2a) = v·T_s/2`.
  At 0.3 m/s this can never exceed `v·T_s`; the R2 value 0.093 m was physically impossible
  for a ramp from 0.3 m/s over 0.25 s.
* The protective stop uses one joint deceleration (`control.stop_decel_joint`, 3.0 rad/s²) in
  the controller and one Cartesian deceleration (`ssm.a_stop`, 1.2 m/s²) in the separation
  distance; the stop duration that results is **measured** in the logs, not assumed.
* The separation distance is `S_p = v_h(T_r+T_s) + v_r T_r + S_s + C + Z_d + Z_r + (v_h+v_r) t_age`,
  evaluated every cycle with the measured `t_age`; the robot speed is limited to the largest
  speed that keeps the measured separation ≥ `S_p` (closed-form, `max_speed_for_separation`).

## Watchdogs (reviewer: 20 Hz watchdog vs 100–105 ms)

* Sensor-stream freshness is checked by the fusion thread at 50 Hz and acted on by the
  control thread every 20 ms cycle, so detection latency is `timeout + [0, 20] ms + age`;
  the measured distribution is reported, not a formula.
* The control-thread watchdog is a separate thread polling every 2 ms; it commands a
  protective stop through the adapter directly when no cycle has completed for
  `period + grace` (60 ms).
* UR robots additionally run a controller-side heartbeat in the URScript (`stale_limit` × 8 ms).

## Communication host ↔ inference device (reviewer: Jetson link)

When `control.learned.remote = true`, each cycle sends one UDP datagram (`InferRequest`,
652 bytes) to `hrc_infer_server` and waits for one reply (`InferReply`, 664 bytes). The
cycle log records the client wall time (`d_learned_ns`, serialisation + network + server) and
the server compute time (`d_remote_compute_ns`, receipt → reply); their difference is
transport + serialisation. There is no GPU code in this repository: the R2 statements on
pinned memory, unified memory and stream synchronisation do not apply and must be removed.

## Baselines

Re-implemented: geometric CBF-QP (`hc_cbf`), ISO/TS 15066 speed-and-separation monitoring
(`ssm`), potential field (`pf`). DMPC, SVO-CBF and RRT-CBF from the earlier study are **not**
re-implemented; the comparison table shrinks to three baselines (six pre-specified hypotheses,
Holm-corrected), unless they are rebuilt.

## Fault model

Rates are design parameters (`cfg/fault_rates.md`); there are no external sources. Poisson,
clustered and Weibull arrivals are available for the sensitivity analysis.

## Simulation backends

* Robot: URSim (vendor controller software, via the real RTDE adapter) when available;
  otherwise the built-in kinematic simulator (`backend: sim`). Results must state which.
* Human and cameras: always the built-in scripted operator and camera model
  (`src/sim/sim.cpp`), with the noise and occlusion parameters in the config.
* PLC: vendor simulators, timed with `tools/worklog.py`.

## Integration layer

Modbus TCP (FC 01/03/04/05/06/15/16) and REST are self-contained; OPC-UA requires open62541
(built automatically when found). Joint velocity registers use 0.01 rad/s resolution (R2:
0.1 rad/s).
