// SPDX-License-Identifier: MIT
#include "hrc/supervisor.hpp"

#include <algorithm>

#include "hrc/run_logger.hpp"

namespace hrc {

const char* to_string(Mode m) {
  switch (m) {
    case Mode::Nominal: return "nominal";
    case Mode::LowConfidence: return "low_confidence";
    case Mode::DegradedStream: return "degraded_stream";
    case Mode::GeometricFallback: return "geometric_fallback";
    case Mode::OverrunShed: return "overrun_shed";
    case Mode::ProtectiveStop: return "protective_stop";
    case Mode::ProtectiveStopLatched: return "protective_stop_latched";
    case Mode::EmergencyStop: return "emergency_stop";
  }
  return "?";
}

// Raises immediately; clears only after the raw condition has been false for clear_s.
void Supervisor::set(FaultCategory c, Cond& k, bool raw, int64_t now, double clear_s, int detail, const char* tag) {
  if (raw) {
    k.clear_since = 0;
    if (!k.active) {
      k.active = true;
      k.since = now;
      if (ev_) ev_->emit(EventKind::FaultDetected, static_cast<uint8_t>(c), 0, detail, tag);
    }
  } else if (k.active) {
    if (k.clear_since == 0) k.clear_since = now;
    if (now - k.clear_since >= static_cast<int64_t>(clear_s * 1e9)) {
      k.active = false;
      if (ev_) ev_->emit(EventKind::FaultCleared, static_cast<uint8_t>(c), (now - k.since) * 1e-9, detail, tag);
    }
  }
}

Mode Supervisor::update(const SupervisorInputs& in) {
  const int64_t now = in.now_ns;
  // --- estimate availability (sensor side)
  const bool est_stale = !in.estimate_available || in.estimate_age_ns > static_cast<int64_t>(p_.estimate_hold_ms * 1e6);
  const bool est_unavailable = est_stale || in.streams_alive == 0 || in.mean_conf < p_.conf_stop;
  set(FaultCategory::TrackingLoss, stop_est_, est_unavailable, now, p_.resume_after_s, in.streams_alive, "estimate_unavailable");
  set(FaultCategory::TrackingLoss, low_conf_, !est_unavailable && in.mean_conf < p_.conf_low, now, p_.hold_clear_s, 0, "low_confidence");
  set(FaultCategory::SensorTimeout, stream_, !est_unavailable && in.streams_alive < in.streams_total, now,
      p_.stream_clear_s, in.streams_total - in.streams_alive, "stream_timeout");

  // --- learned barrier health
  if (in.learned_failed || in.qp_relaxed) fallback_until_ = now + static_cast<int64_t>(p_.fallback_hold_s * 1e9);
  // a degradation of the learned component, not a fault of the taxonomy: category None
  set(FaultCategory::None, fallback_, now < fallback_until_, now, 0.0, in.learned_failed ? 1 : 2, "learned_fallback");

  // --- overruns
  consecutive_overruns_ = in.previous_cycle_overrun ? consecutive_overruns_ + 1 : 0;
  set(FaultCategory::ComputationalOverrun, overrun_, in.previous_cycle_overrun, now, 0.0, consecutive_overruns_, "deadline_overrun");
  const bool wd = watchdog_tripped_.exchange(false);
  if (wd && ev_) ev_->emit(EventKind::FaultDetected, static_cast<uint8_t>(FaultCategory::ComputationalOverrun), 0, 0, "watchdog_stop");
  set(FaultCategory::ComputationalOverrun, stop_overrun_, wd || consecutive_overruns_ >= p_.consecutive_overrun_stop, now,
      p_.resume_after_s, 0, "overrun_stop");

  // --- robot communication
  comm_errors_ = in.robot_comm_error ? comm_errors_ + 1 : 0;
  set(FaultCategory::HardwareCommunication, stop_comm_, comm_errors_ >= p_.comm_retries, now, p_.resume_after_s,
      comm_errors_, "comm_retries_exhausted");
  if (!latched_partition_ && in.robot_state_age_ns > static_cast<int64_t>(p_.partition_timeout_ms * 1e6)) {
    latched_partition_ = true;
    if (ev_) ev_->emit(EventKind::FaultDetected, static_cast<uint8_t>(FaultCategory::NetworkPartition),
                       in.robot_state_age_ns * 1e-6);
  }
  // --- constraint violation (separation floor crossed by more than the threshold)
  if (!latched_violation_ && in.estimate_available && in.h_geo < p_.violation_threshold) {
    latched_violation_ = true;
    if (ev_) ev_->emit(EventKind::FaultDetected, static_cast<uint8_t>(FaultCategory::ConstraintViolation), in.h_geo);
  }
  if (!estop_ && in.memory_fault) {
    estop_ = true;
    if (ev_) ev_->emit(EventKind::FaultDetected, static_cast<uint8_t>(FaultCategory::MemoryAllocation));
  }
  if (in.config_rejected && ev_)
    ev_->emit(EventKind::FaultDetected, static_cast<uint8_t>(FaultCategory::ConfigurationInconsistency));

  // --- strict priority: most severe active condition wins
  Mode m = Mode::Nominal;
  if (low_conf_.active) m = Mode::LowConfidence;
  if (stream_.active) m = std::max(m, Mode::DegradedStream);
  if (fallback_.active) m = std::max(m, Mode::GeometricFallback);
  if (overrun_.active) m = std::max(m, Mode::OverrunShed);
  if (stop_est_.active || stop_comm_.active || stop_overrun_.active) m = std::max(m, Mode::ProtectiveStop);
  if (latched_partition_ || latched_violation_) m = std::max(m, Mode::ProtectiveStopLatched);
  if (estop_) m = Mode::EmergencyStop;
  if (m != mode_) {
    if (ev_) ev_->emit(EventKind::ModeChange, 0, 0, 0, to_string(m), static_cast<uint8_t>(mode_), static_cast<uint8_t>(m));
    mode_ = m;
  }
  return mode_;
}

void Supervisor::acknowledge(int64_t now_ns) {
  (void)now_ns;
  if (latched_partition_ || latched_violation_ || estop_) {
    if (ev_) ev_->emit(EventKind::OperatorAck, 0, 0, (latched_partition_ ? 1 : 0) | (latched_violation_ ? 2 : 0) | (estop_ ? 4 : 0));
    if (latched_partition_ && ev_) ev_->emit(EventKind::FaultCleared, static_cast<uint8_t>(FaultCategory::NetworkPartition));
    if (latched_violation_ && ev_) ev_->emit(EventKind::FaultCleared, static_cast<uint8_t>(FaultCategory::ConstraintViolation));
    if (estop_ && ev_) ev_->emit(EventKind::FaultCleared, static_cast<uint8_t>(FaultCategory::MemoryAllocation));
  }
  latched_partition_ = latched_violation_ = estop_ = false;
}

void Supervisor::watchdog_trip(int64_t) { watchdog_tripped_.store(true); }

}  // namespace hrc
