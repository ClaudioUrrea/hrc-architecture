// SPDX-License-Identifier: MIT
// The four interface contracts. The safety module (src/safety) and the control layer
// (src/control) depend on this header and on types.hpp only; they must build and pass
// their tests with no vendor SDK present (enforced by the target `hrc_safety_isolated`).
#pragma once
#include <cstdint>
#include "hrc/types.hpp"

namespace hrc {

// ---------------------------------------------------------------- physical layer
class IRobotController {
 public:
  virtual ~IRobotController() = default;
  virtual const char* name() const = 0;
  // lifecycle
  virtual Result connect(const ConnectionConfig& cfg) = 0;
  virtual Result disconnect() = 0;
  virtual bool isConnected() const = 0;
  // cyclic path (called from the real-time thread; implementations must not allocate)
  virtual Result getCurrentState(RobotState& out) = 0;              // latest received state, non-blocking
  virtual Result streamJointVelocity(const Joints& qd, double dt_s) = 0;
  virtual Result setOverride(double factor) = 0;                    // factor in [0,1]
  virtual Result protectiveStop(double decel_rad_s2) = 0;
  virtual Result emergencyStop() = 0;
  virtual HealthStatus getHealthStatus() const = 0;
  // configuration / acknowledgement
  virtual Result moveJoint(const Joints& target, double vel_rad_s) = 0;  // point-to-point, non-cyclic
  virtual Limits getKinematicLimits() const = 0;
  virtual Result resetFault() = 0;
};

class ISensorFusion {
 public:
  virtual ~ISensorFusion() = default;
  virtual bool start() = 0;
  virtual void stop() = 0;
  // Copies the latest published estimate. Wait-free for the reader.
  virtual bool latest(HumanState& out) const = 0;
};

// ---------------------------------------------------------------- control layer
constexpr int kMaxConstraintRows = 16;

// One linearized barrier row:  dh/dq . qd  >=  rhs   (rhs already contains -kappa*h and the
// worst-case human-motion term).
struct ConstraintRow {
  double h = 0;
  double rhs = 0;
  std::array<double, kMaxDof> a{};
};

struct ConstraintSet {
  int n = 0;
  bool trustworthy = true;   // false: the producing model abstains (gray zone / invalid input)
  double h_min = 1e9;        // smallest barrier value of the set (for logging)
  std::array<ConstraintRow, kMaxConstraintRows> rows{};
  void clear() { n = 0; trustworthy = true; h_min = 1e9; }
};

class ISafetyConstraint {
 public:
  virtual ~ISafetyConstraint() = default;
  virtual const char* name() const = 0;
  virtual bool evaluate(const RobotState& rs, const HumanState& hs, ConstraintSet& out) = 0;
  virtual double margin() const = 0;
  virtual bool isTrustworthy() const = 0;
};

struct Task {
  Joints q_goal;
  double gain = 1.5;  // 1/s
};

class IController {
 public:
  virtual ~IController() = default;
  virtual void computeNominal(const RobotState& rs, const Task& task, Joints& qd_nom) = 0;
};

// ---------------------------------------------------------------- faults
enum class FaultCategory : uint8_t {
  None = 0,
  SensorTimeout,
  NetworkPartition,
  ComputationalOverrun,
  TrackingLoss,
  HardwareCommunication,
  MemoryAllocation,
  ConfigurationInconsistency,
  ConstraintViolation,
};
const char* to_string(FaultCategory c);

struct FaultEvent {
  int64_t t_ns = 0;
  FaultCategory category = FaultCategory::None;
  bool raised = true;  // false = cleared
  int32_t detail = 0;
};

class IFaultObserver {
 public:
  virtual ~IFaultObserver() = default;
  virtual void onFault(const FaultEvent& e) = 0;
};

}  // namespace hrc
