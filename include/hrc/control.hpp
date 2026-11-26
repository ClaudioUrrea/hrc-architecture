// SPDX-License-Identifier: MIT
// Nominal controller, task sequencing and the safety strategies compared in the paper.
#pragma once
#include <string>
#include <vector>

#include "hrc/interfaces.hpp"
#include "hrc/safety.hpp"

namespace hrc {

class JointPController final : public IController {
 public:
  explicit JointPController(const Joints& qd_max) : qd_max_(qd_max) {}
  void computeNominal(const RobotState& rs, const Task& task, Joints& qd_nom) override;

 private:
  Joints qd_max_;
};

// Cycles through joint-space waypoints; one pass through the list is one task cycle.
class TaskSequencer {
 public:
  TaskSequencer(std::vector<Joints> waypoints, double tol_rad, double dwell_s);
  // Returns true exactly on the cycle in which a task cycle completes; *cycle_s receives its duration.
  bool update(const RobotState& rs, int64_t now_ns, Task& task, double* cycle_s);
  int completed() const { return completed_; }

 private:
  std::vector<Joints> wp_;
  double tol_, dwell_;
  size_t idx_ = 0;
  int64_t reached_at_ = 0, cycle_start_ = 0;
  int completed_ = 0;
};

enum class Strategy { Proposed, HcCbf, Ssm, PotentialField };
Strategy strategy_from_string(const std::string& s);
const char* to_string(Strategy s);

struct PotentialFieldParams {
  double d0 = 0.5;      // influence distance (m)
  double k_rep = 0.08;  // repulsion gain
};

}  // namespace hrc
