// SPDX-License-Identifier: MIT
// Safety supervisor: one state machine that maps every active fault condition to an
// operating mode. The rule is a strict priority order: the most severe active condition
// determines the mode, so two policies can never disagree about what the cell does.
//
//   severity  mode                       entered when                                         leaves when
//   0         NOMINAL                    no condition active                                  -
//   1         LOW_CONFIDENCE             0.4 <= mean keypoint confidence < 0.6                conf >= 0.6 for hold_clear_s
//   2         DEGRADED_STREAM            >=1 camera stream silent > stream_timeout_ms,        all streams fresh for
//                                        fused estimate still available                       stream_clear_s
//   3         GEOMETRIC_FALLBACK         learned barrier failed (timeout, overrun, QP relax)  fallback_hold_s elapsed
//   4         OVERRUN_SHED               a cycle exceeded the deadline                        next on-time cycle
//   5         PROTECTIVE_STOP            estimate unavailable: no stream alive, OR estimate   condition clear for
//                                        older than estimate_hold_ms, OR mean conf < 0.4;     resume_after_s (automatic)
//                                        robot comm fault after comm_retries; overruns
//                                        on consecutive_overrun_stop cycles; watchdog stop
//                                        of a control thread that missed its heartbeat
//   6         PROTECTIVE_STOP_LATCHED    network partition (no robot state for                operator acknowledgement
//                                        partition_timeout_ms); constraint violation
//                                        (h_geo < violation_threshold)
//   7         EMERGENCY_STOP             memory allocation failure                            operator acknowledgement
//
// Speed scale and separation floor applied per mode are in SupervisorParams.
#pragma once
#include <array>
#include <atomic>
#include <cstdint>

#include "hrc/interfaces.hpp"

namespace hrc {

enum class Mode : uint8_t {
  Nominal = 0,
  LowConfidence = 1,
  DegradedStream = 2,
  GeometricFallback = 3,
  OverrunShed = 4,
  ProtectiveStop = 5,
  ProtectiveStopLatched = 6,
  EmergencyStop = 7,
};
const char* to_string(Mode m);
constexpr int kNumModes = 8;

struct SupervisorParams {
  double conf_stop = 0.4, conf_low = 0.6;
  double estimate_hold_ms = 100;      // max estimate age before the estimate counts as unavailable
  double stream_timeout_ms = 100;     // per camera
  double stream_clear_s = 5.0;
  double hold_clear_s = 1.0;
  double fallback_hold_s = 5.0;
  double resume_after_s = 1.0;
  int consecutive_overrun_stop = 5;
  int comm_retries = 3;
  double partition_timeout_ms = 150;  // no new robot state for this long -> partition
  double violation_threshold = -0.05; // h_geo below this (m) -> constraint violation
  std::array<double, kNumModes> speed_scale{1.0, 0.7, 0.5, 0.5, 1.0, 0.0, 0.0, 0.0};
  std::array<double, kNumModes> floor_m{0.15, 0.225, 0.15, 0.30, 0.15, 0.15, 0.15, 0.15};
};

// Inputs observed by the control thread each cycle.
struct SupervisorInputs {
  int64_t now_ns = 0;
  bool robot_state_valid = false;
  int64_t robot_state_age_ns = 0;
  bool robot_comm_error = false;
  bool estimate_available = false;
  int64_t estimate_age_ns = 0;
  int streams_alive = 0, streams_total = 0;
  double mean_conf = 0;
  double h_geo = 1e9;
  bool learned_failed = false;     // timeout / not finite / inference overrun
  bool qp_relaxed = false;
  bool previous_cycle_overrun = false;
  bool memory_fault = false;
  bool config_rejected = false;    // reported, never changes the mode
};

class EventChannel;

class Supervisor {
 public:
  explicit Supervisor(const SupervisorParams& p, EventChannel* ev = nullptr) : p_(p), ev_(ev) {}
  Mode update(const SupervisorInputs& in);
  Mode mode() const { return mode_; }
  double speed_scale() const { return p_.speed_scale[static_cast<size_t>(mode_)]; }
  double floor() const { return p_.floor_m[static_cast<size_t>(mode_)]; }
  bool learned_allowed() const { return mode_ == Mode::Nominal || mode_ == Mode::LowConfidence || mode_ == Mode::OverrunShed; }
  bool stopped() const { return mode_ >= Mode::ProtectiveStop; }
  // Operator acknowledgement (real HMI or the simulated operator of the experiment harness).
  void acknowledge(int64_t now_ns);
  // Raised by the watchdog thread when the control thread misses its heartbeat (thread-safe).
  void watchdog_trip(int64_t now_ns);
  const SupervisorParams& params() const { return p_; }

 private:
  struct Cond {
    bool active = false;
    int64_t since = 0, clear_since = 0;
  };
  void set(FaultCategory c, Cond& k, bool raw, int64_t now, double clear_s, int detail, const char* tag);
  SupervisorParams p_;
  EventChannel* ev_;
  Mode mode_ = Mode::Nominal;
  Cond low_conf_, stream_, fallback_, overrun_, stop_est_, stop_comm_, stop_overrun_;
  bool latched_partition_ = false, latched_violation_ = false, estop_ = false;
  std::atomic<bool> watchdog_tripped_{false};
  int consecutive_overruns_ = 0, comm_errors_ = 0;
  int64_t fallback_until_ = 0;
};

}  // namespace hrc
