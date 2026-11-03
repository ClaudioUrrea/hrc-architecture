// SPDX-License-Identifier: MIT
// Safety layer: geometric barrier, learned barrier, ISO/TS 15066 speed-and-separation
// monitoring and the QP safety filter. Depends only on interfaces.hpp/types.hpp/kinematics.hpp.
#pragma once
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "hrc/interfaces.hpp"
#include "hrc/kinematics.hpp"

namespace hrc {

// ---------------------------------------------------------------------------- shared params
struct HumanMotionModel {
  // How the barrier accounts for human motion between estimate and actuation (approach speed
  // of a keypoint towards the robot, used both for the motion term and for the data age):
  //   "bound"      (default) a fixed design bound v_bound for every keypoint
  //   "measured"   measured keypoint velocity + v_margin, capped at v_max
  //   "worst_case" v_max for every keypoint, each moving independently
  // The guarantee of the barrier holds only while real keypoint speeds respect the bound used.
  bool worst_case = false;
  bool measured = false;
  double v_bound = 1.0;        // m/s
  double v_max = 2.0;          // m/s
  double v_margin = 0.3;       // m/s
};

// ---------------------------------------------------------------------------- geometric CBF
struct GeometricCbfParams {
  double r_safety = 0.15;      // separation floor (m)
  double kappa = 2.0;          // class-K gain (1/s)
  int max_rows = 6;            // closest (link point, keypoint) pairs turned into rows
  double min_keypoint_conf = 0.2;
  // 3.1: margin for the error of the estimated keypoint position (m), subtracted from every
  // barrier value. 0 reproduces release 3.0 (no position-uncertainty term in the barrier).
  double position_margin = 0.0;
  HumanMotionModel motion;
};

class GeometricCbf final : public ISafetyConstraint {
 public:
  GeometricCbf(const DhParams& dh, const GeometricCbfParams& p);
  const char* name() const override { return "geometric_cbf"; }
  bool evaluate(const RobotState& rs, const HumanState& hs, ConstraintSet& out) override;
  double margin() const override { return p_.r_safety; }
  bool isTrustworthy() const override { return true; }
  void set_floor(double r) { p_.r_safety = r; }
  // Re-expresses rows already evaluated in `cs` for a new separation floor (h and rhs are affine
  // in the floor), so a floor raised by the supervisor in this cycle applies in this cycle.
  void retighten(ConstraintSet& cs, double new_floor);
  double floor() const { return p_.r_safety; }
  double last_min_separation() const { return last_min_sep_; }  // surface-to-keypoint distance (m)
  Vec3 last_closest_keypoint() const { return last_kp_; }
  double last_max_link_speed() const { return last_link_speed_; }
  // Largest Cartesian speed of any sampled link point for joint velocity qd at the last evaluated q.
  double link_speed(const Joints& qd) const;
  void set_data_age(double age_s) { age_s_ = age_s; }
  Kinematics& kinematics() { return kin_; }

 private:
  Kinematics kin_;
  GeometricCbfParams p_;
  double last_min_sep_ = 1e9, last_link_speed_ = 0, age_s_ = 0;
  Vec3 last_kp_;
  struct Pair { double d; int pi; int kj; };
  std::vector<Pair> pairs_;
};

// ---------------------------------------------------------------------------- learned CBF
// Multilayer perceptron h_theta(q, p_h) with leaky-ReLU hidden layers, exported by
// train/train_cbf.py. Evaluated locally on the CPU, or on a remote inference server
// (apps/hrc_infer_server) reached over UDP, in which case transport and server compute
// are timed separately.
struct MlpLayer {
  int in = 0, out = 0;
  std::vector<double> W;  // row-major out x in
  std::vector<double> b;
};

class Mlp {
 public:
  bool load(const std::string& path, std::string& err);
  // Forward pass and gradient of the scalar output with respect to the input.
  double forward_grad(const double* x, double* grad_x);
  int input_dim() const { return layers_.empty() ? 0 : layers_.front().in; }
  double alpha() const { return alpha_; }
  const std::string& sha256() const { return sha_; }
  // input normalisation shipped with the weights
  std::vector<double> x_mean, x_scale;
  double out_scale = 1.0;

 private:
  std::vector<MlpLayer> layers_;
  double alpha_ = 0.01;
  std::vector<std::vector<double>> act_, pre_;
  std::vector<double> gbuf_a_, gbuf_b_;
  std::string sha_;
};

struct LearnedCbfParams {
  std::string weights_path;
  double kappa = 2.0;
  double gray_band = 0.15;     // |h| < gray_band -> the model abstains for this cycle
  HumanMotionModel motion;
  // remote inference
  bool remote = false;
  std::string remote_host = "127.0.0.1";
  int remote_port = 47011;
  int remote_timeout_us = 5000;
};

struct LearnedTiming {
  int64_t total_ns = 0;          // client wall time
  int64_t remote_compute_ns = 0; // reported by server
  bool remote = false, timeout = false;
};

class LearnedCbf final : public ISafetyConstraint {
 public:
  LearnedCbf(const DhParams& dh, const LearnedCbfParams& p);
  ~LearnedCbf() override;
  bool ok() const { return ok_; }
  const std::string& error() const { return err_; }
  const char* name() const override { return "learned_cbf"; }
  bool evaluate(const RobotState& rs, const HumanState& hs, ConstraintSet& out) override;
  double margin() const override { return p_.gray_band; }
  bool isTrustworthy() const override { return trusted_; }
  double last_h() const { return last_h_; }
  const LearnedTiming& timing() const { return timing_; }
  const Mlp& model() const { return mlp_; }
  // Builds the 66-dim (or n+60) input exactly as the training script does.
  static void build_input(const DhParams& dh, const RobotState& rs, const HumanState& hs, double* x);

 private:
  bool remote_eval(const double* x, int nx, double& h, double* grad);
  DhParams dh_;
  LearnedCbfParams p_;
  Mlp mlp_;
  bool ok_ = false, trusted_ = false;
  std::string err_;
  double last_h_ = 0;
  LearnedTiming timing_;
  int sock_ = -1;
  uint32_t seq_ = 0;
  std::vector<double> x_, g_;
};

// ---------------------------------------------------------------------------- SSM (ISO/TS 15066 5.5.4)
struct SsmParams {
  double v_h = 1.6;      // human speed (m/s), ISO/TS 15066 / ISO 13855 value
  double T_r = 0.10;     // robot system reaction time (s), incl. one control period + detection
  double a_stop = 1.2;   // robot Cartesian deceleration during a protective stop (m/s^2)
  double C = 0.20;       // intrusion distance (m)
  double Z_d = 0.04;     // human position uncertainty (m)
  double Z_r = 0.001;    // robot position uncertainty (m)
};

struct PsdTerms {
  double v_r = 0, T_s = 0, S_h = 0, S_r = 0, S_s = 0, S_age = 0, total = 0;
};

// Protective separation distance at robot speed v_r with sensing-data age t_age.
// Constant deceleration a_stop: T_s = v_r / a_stop, S_s = v_r^2 / (2 a_stop) = v_r T_s / 2.
PsdTerms protective_separation(const SsmParams& p, double v_r, double t_age);
// Largest robot speed for which protective_separation(v, t_age).total <= separation.
// Returns 0 if even v = 0 violates.
double max_speed_for_separation(const SsmParams& p, double separation, double t_age);

// ---------------------------------------------------------------------------- QP safety filter
// min ||qd - qd_nom||^2  s.t.  a_i . qd >= rhs_i,  |qd_j| <= qd_max_j
// Solved by Hildreth's dual coordinate ascent (exact for strictly convex QPs; finite rows).
struct QpResult {
  bool feasible = false;
  int iters = 0;
  double max_violation = 0;
};

class QpFilter {
 public:
  QpResult solve(const Joints& qd_nom, const Joints& qd_max, const ConstraintSet* const* sets, int nsets,
                 Joints& qd_out, int max_iters = 200, double tol = 1e-7);
};

// ---------------------------------------------------------------------------- limited safety filter (3.1)
// The barrier QP with EVERY speed limit inside the problem, so the dispatched command is a QP
// solution and satisfies every active barrier row (src/safety/limited_filter.cpp):
//   * supervisor speed scale s_mode: box s_mode*qd_max and nominal s_mode*qd_nom;
//   * SSM link-speed limit v_ok (ISO/TS 15066 5.5.4), if v_ok >= 0: when the solution's largest
//     link-point speed exceeds v_ok, the envelope fraction sigma is backed off (3.0 ratio
//     sigma*v_ok/v, then halved, finally 0) and the QP RE-SOLVED each time; never scaled afterwards;
//   * learned rows that make the problem infeasible are dropped (geometric rows kept), as in 3.0;
//   * explicit outcomes when the rows cannot be met: qp_failed (infeasible even at full speed) or
//     limit_conflict (feasible at full speed, not within the speed limits) -> stop.
// Release 3.0 multiplied the QP solution by s_mode and the SSM ratio after solving, which can
// violate a row with rhs > 0 (Reviewer 2, round 4).
struct LimitedFilterResult {
  bool stop = false;
  bool relaxed = false, qp_failed = false, limit_conflict = false, ssm_reduced = false;
  double sigma = 0;   // envelope fraction used (0 when stopped)
  int iters = 0;
};
LimitedFilterResult limited_filter(QpFilter& qp, const GeometricCbf& geo, const Joints& qd_nom, const Joints& qd_max,
                                   double s_mode, double v_ok, const ConstraintSet* geo_rows,
                                   const ConstraintSet* learned_rows, Joints& qd_out);
// Largest violation of a command: rows (normalised, m/s), box s_mode*qd_max (rad/s) and, if v_ok >= 0,
// SSM link speed (m/s). <= 1e-6 means the command satisfies every limit. Used as the final check
// of the command actually dispatched, for every strategy.
double command_violation(const GeometricCbf& geo, const Joints& qd, const Joints& qd_max, double s_mode, double v_ok,
                         const ConstraintSet* const* sets, int nsets);

}  // namespace hrc
