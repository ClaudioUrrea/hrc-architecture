// SPDX-License-Identifier: MIT
// Binary record layouts written by the logger. The layout is mirrored by
// analysis/hrc_logs.py and described field by field in each run's schema.json,
// so a run directory is readable without this source tree.
#pragma once
#include <cstdint>

namespace hrc {

enum CycleFlag : uint16_t {
  kFlagOverrun = 1u << 0,           // record completed after the deadline (3.1: the deadline counted in the
                                    // run summary and seen by the supervisor is judged at enqueue completion)
  kFlagInjectedOverrun = 1u << 1,   // an overrun was injected into this cycle by the fault injector
  kFlagQpRelaxed = 1u << 2,         // learned rows dropped, geometric rows kept, re-solved
  kFlagQpFailed = 1u << 3,          // geometric-only problem infeasible -> stop command
  kFlagLearnedUntrusted = 1u << 4,  // learned barrier abstained (gray zone) or unavailable
  kFlagEstimateUnavailable = 1u << 5,
  kFlagReleaseLate = 1u << 6,       // wake-up later than planned release by > 1 period
  kFlagStopCommanded = 1u << 7,
  kFlagRemoteInference = 1u << 8,   // barrier evaluated on the remote inference server
  kFlagRemoteTimeout = 1u << 9,
  // release 3.1
  kFlagLimitConflict = 1u << 10,    // barrier rows feasible at full speed but not within the speed limits -> stop
  kFlagSsmReduced = 1u << 11,       // the SSM speed limit reduced the command (QP re-solved, rows kept)
  kFlagFinalCheckFailed = 1u << 12, // dispatched command failed the final row/box/SSM check -> stop
};

#pragma pack(push, 1)
struct CycleRecord {           // 208 bytes (192 in release 3.0)
  uint64_t idx;                // cycle index within the run
  int64_t t_release_ns;        // planned release (absolute, CLOCK_MONOTONIC)
  int64_t t_wake_ns;           // actual wake-up
  int64_t t_end_ns;            // record complete, immediately before it is enqueued to the logger;
                               // execution time = t_end_ns - t_wake_ns + d_enqueue_prev_ns of the NEXT record
  int32_t d_state_ns;          // read robot state + human estimate
  int32_t d_nominal_ns;        // nominal controller
  int32_t d_geo_ns;            // geometric barrier rows
  int32_t d_learned_ns;        // learned barrier incl. transport when remote (client-side wall time)
  int32_t d_remote_compute_ns; // server-reported compute time (0 if local)
  int32_t d_qp_ns;             // QP safety filter (all attempts)
  int32_t d_dispatch_ns;       // command serialisation + adapter call
  int32_t d_log_ns;            // bookkeeping incl. this record
  float h_geo;                 // smallest geometric barrier value (m)
  float h_learned;             // learned barrier value (normalised), NaN if not evaluated
  float min_sep_m;             // minimum robot-human separation (m)
  float human_age_ms;          // now - t_obs of the estimate used
  float psd_m;                 // protective separation distance used this cycle (m)
  float speed_scale;           // final speed scaling applied
  float qd_norm;               // |commanded joint velocity|
  float mean_conf;             // mean keypoint confidence of the estimate used
  uint16_t flags;              // CycleFlag
  uint8_t mode;                // SupervisorMode
  uint8_t qp_iters;
  uint8_t qp_rows;
  uint8_t streams_alive;
  float q[7];                  // measured joint positions used this cycle (rad)
  float qd_cmd[7];             // commanded joint velocities (rad/s), 0 when stopping
  float closest_kp[3];         // position of the keypoint closest to the robot (m, cell frame)
  // ---- release 3.1
  float gt_min_sep_m;          // ground-truth separation (simulator robot state + scripted human), NaN if unavailable
  float est_err_max_m;         // largest keypoint error of the estimate used vs ground truth at its observation time
  float final_viol;            // largest violation of the dispatched command: barrier rows (normalised, m/s),
                               // joint box (rad/s) and SSM link speed (m/s); 0 if a stop was decided earlier.
                               // > 1e-6 only together with kFlagFinalCheckFailed (the command was then replaced by a stop)
  float v_ssm_ok;              // SSM speed limit this cycle (m/s), -1 if SSM inactive
  float qd_meas_norm;          // |measured joint velocity| (rad/s): distinguishes deceleration from standstill
  int32_t d_enqueue_prev_ns;   // duration of the logger enqueue of the PREVIOUS cycle (-1 for idx 0)
  uint8_t cond_mask;           // supervisor conditions active this cycle (bit k <=> condition of mode k)
  float gt_age_ms;             // age of the ground-truth sample at dispatch (probe thread, 250 Hz), NaN if none
  float est_err_closest_m;     // error of the estimate's keypoint closest to the robot vs ground truth at its observation time
  uint8_t pad[5];
};
#pragma pack(pop)
static_assert(sizeof(CycleRecord) == 208, "CycleRecord layout changed: update schema_json() and the analysis");

enum class EventKind : uint8_t {
  Info = 0,
  FaultInjected = 1,
  FaultDetected = 2,
  FaultCleared = 3,
  ModeChange = 4,
  RecoveryComplete = 5,
  OperatorAck = 6,
  ProtocolSample = 7,
  ConformanceItem = 8,
  Warning = 9,
};

struct EventRecord {
  int64_t t_ns;
  EventKind kind;
  uint8_t category;  // FaultCategory
  uint8_t a;         // e.g. old mode
  uint8_t b;         // e.g. new mode
  int32_t detail;
  double value;
  char text[40];
};

}  // namespace hrc
