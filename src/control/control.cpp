// SPDX-License-Identifier: MIT
#include "hrc/control.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace hrc {

void JointPController::computeNominal(const RobotState& rs, const Task& task, Joints& qd) {
  qd.n = rs.q.n;
  // saturate the joint-space error uniformly so that the path stays a straight line in joint space
  double scale = 1.0;
  for (int i = 0; i < qd.n; ++i) {
    double v = task.gain * (task.q_goal[i] - rs.q[i]);
    if (std::fabs(v) > qd_max_[i]) scale = std::min(scale, qd_max_[i] / std::fabs(v));
  }
  for (int i = 0; i < qd.n; ++i) qd[i] = task.gain * (task.q_goal[i] - rs.q[i]) * scale;
}

TaskSequencer::TaskSequencer(std::vector<Joints> wp, double tol, double dwell) : wp_(std::move(wp)), tol_(tol), dwell_(dwell) {
  if (wp_.empty()) throw std::runtime_error("TaskSequencer: no waypoints");
}

bool TaskSequencer::update(const RobotState& rs, int64_t now, Task& task, double* cycle_s) {
  if (cycle_start_ == 0) cycle_start_ = now;
  task.q_goal = wp_[idx_];
  double err = 0;
  for (int i = 0; i < rs.q.n; ++i) err = std::max(err, std::fabs(wp_[idx_][i] - rs.q[i]));
  if (err > tol_) { reached_at_ = 0; return false; }
  if (reached_at_ == 0) reached_at_ = now;
  if ((now - reached_at_) * 1e-9 < dwell_) return false;
  reached_at_ = 0;
  idx_ = (idx_ + 1) % wp_.size();
  task.q_goal = wp_[idx_];
  if (idx_ == 0) {
    if (cycle_s) *cycle_s = (now - cycle_start_) * 1e-9;
    cycle_start_ = now;
    ++completed_;
    return true;
  }
  return false;
}

Strategy strategy_from_string(const std::string& s) {
  if (s == "proposed") return Strategy::Proposed;
  if (s == "hc_cbf") return Strategy::HcCbf;
  if (s == "ssm") return Strategy::Ssm;
  if (s == "pf" || s == "potential_field") return Strategy::PotentialField;
  throw std::runtime_error("unknown strategy: " + s);
}
const char* to_string(Strategy s) {
  switch (s) {
    case Strategy::Proposed: return "proposed";
    case Strategy::HcCbf: return "hc_cbf";
    case Strategy::Ssm: return "ssm";
    case Strategy::PotentialField: return "pf";
  }
  return "?";
}

}  // namespace hrc
