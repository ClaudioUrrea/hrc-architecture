// SPDX-License-Identifier: MIT
// Binary record layouts written by the logger. The layout is mirrored by
// analysis/hrc_logs.py and described field by field in each run's schema.json,
// so a run directory is readable without this source tree.
#pragma once
#include <cstdint>

namespace hrc {

enum CycleFlag : uint16_t {
  kFlagOverrun = 1u << 0,           // cycle execution exceeded the deadline
  kFlagInjectedOverrun = 1u << 1,   // an overrun was injected into this cycle by the fault injector
  kFlagQpRelaxed = 1u << 2,         // learned rows dropped, geometric rows kept, re-solved
  kFlagQpFailed = 1u << 3,          // geometric-only problem infeasible -> stop command
  kFlagLearnedUntrusted = 1u << 4,  // learned barrier abstained (gray zone) or unavailable
  kFlagEstimateUnavailable = 1u << 5,
  kFlagReleaseLate = 1u << 6,       // wake-up later than planned release by > 1 period
  kFlagStopCommanded = 1u << 7,
  kFlagRemoteInference = 1u << 8,   // barrier evaluated on the remote inference server
  kFlagRemoteTimeout = 1u << 9,
};

#pragma pack(push, 1)
struct CycleRecord {           // 192 bytes
  uint64_t idx;                // cycle index within the run
  int64_t t_release_ns;        // planned release (absolute, CLOCK_MONOTONIC)
  int64_t t_wake_ns;           // actual wake-up
  int64_t t_end_ns;            // command written to the outbound path
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
  uint8_t pad[22];
};
#pragma pack(pop)
static_assert(sizeof(CycleRecord) == 192, "CycleRecord must stay 192 bytes");

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
