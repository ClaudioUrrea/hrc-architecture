// SPDX-License-Identifier: MIT
// Built-in simulation backend: a kinematic robot with first-order joint dynamics, a scripted
// human operator and a multi-camera keypoint sensor model. It is a *simulation*: every
// result obtained with it must be labelled as such. Vendor simulators (URSim, Sunrise,
// RobotStudio) are reached through the real adapters instead.
#pragma once
#include <atomic>
#include <cstdint>
#include <mutex>
#include <random>
#include <string>
#include <thread>
#include <vector>

#include "hrc/interfaces.hpp"
#include "hrc/kinematics.hpp"
#include "hrc/spsc.hpp"

namespace hrc {

// ---------------------------------------------------------------------------- robot
struct SimRobotParams {
  DhParams dh = DhParams::ur5e();
  double rate_hz = 500;        // controller servo rate
  double tau_s = 0.02;         // first-order velocity response
  double cmd_latency_ms = 2;   // host->controller
  double state_latency_ms = 2; // controller->host
  Limits limits;
  Joints q0;
};

class SimRobot final : public IRobotController {
 public:
  explicit SimRobot(const SimRobotParams& p);
  ~SimRobot() override;
  const char* name() const override { return "sim_robot"; }
  Result connect(const ConnectionConfig&) override;
  Result disconnect() override;
  bool isConnected() const override { return running_.load(); }
  Result getCurrentState(RobotState& out) override;
  Result streamJointVelocity(const Joints& qd, double dt_s) override;
  Result setOverride(double f) override;
  Result protectiveStop(double decel) override;
  Result emergencyStop() override;
  HealthStatus getHealthStatus() const override;
  Result moveJoint(const Joints& target, double vel) override;
  Limits getKinematicLimits() const override { return p_.limits; }
  Result resetFault() override;
  // fault hooks (thread-safe)
  void inject_partition(double seconds);
  void inject_comm_faults(int n_calls);

 private:
  void loop();
  struct Cmd { int64_t t_ns; Joints qd; bool stop; double decel; };
  SimRobotParams p_;
  std::atomic<bool> running_{false}, estop_{false};
  std::thread th_;
  SeqlockSlot<Cmd> cmd_;
  std::vector<RobotState> hist_;  // ring of past states for latency
  size_t hist_head_ = 0;
  SeqlockSlot<RobotState> visible_;
  std::atomic<double> override_{1.0};
  std::atomic<int64_t> partition_until_{0};
  std::atomic<int> comm_faults_{0};
  std::atomic<uint32_t> seq_{0};
};

// ---------------------------------------------------------------------------- human
struct HumanScriptParams {
  std::string scenario = "pick_and_place";  // pick_and_place | screwdriving | inspection | material_handling | mixed | continuous
  double walk_speed = 1.2;     // m/s
  double reach_speed = 1.0;    // m/s, hand
  double v_cap = 1.6;          // m/s, bound respected by the script outside injected lunges
  double shared_zone_x = 0.55; // m, distance of the shared bench from the robot base
  double cycle_s = 18;         // task cycle of the scenario
  uint64_t seed = 1;
};

class SimHuman {
 public:
  explicit SimHuman(const HumanScriptParams& p);
  // Ground-truth keypoints at time t (s since start). Deterministic for a given seed.
  void keypoints(double t, std::array<Vec3, kKeypoints>& kp) const;
  // Injected lunge: right hand moves toward `target` at `speed` from t0 for `dur` seconds.
  void inject_lunge(double t0, double dur, const Vec3& target, double speed);
  const HumanScriptParams& params() const { return p_; }

 private:
  HumanScriptParams p_;
  struct Lunge { double t0, dur, speed; Vec3 target; };
  mutable std::mutex mu_;
  std::vector<Lunge> lunges_;
  std::vector<double> phase_jitter_;
};

// ---------------------------------------------------------------------------- cameras
struct CameraParams {
  int n = 6;
  double fps = 30;
  double latency_ms = 45;            // acquisition -> keypoints available (depth + pose network)
  double sigma0_m = 0.010;           // depth noise at 1 m
  double sigma_quad = 0.008;         // additional noise per m^2 of range
  double occlusion_prob = 0.15;      // per keypoint per camera
  double ring_radius_m = 2.2;
  double height_m = 2.4;
  uint64_t seed = 2;
};

struct CameraFrame {
  int64_t t_acq_ns = 0, t_avail_ns = 0;
  int64_t frame = -1;
  std::array<Vec3, kKeypoints> kp{};
  std::array<double, kKeypoints> conf{};
  std::array<double, kKeypoints> sigma{};
};

class SimCameraArray {
 public:
  SimCameraArray(const CameraParams& p, const SimHuman& human, int64_t t0_ns);
  // Latest frame of camera c available at time now; false if the stream is dead.
  bool latest(int c, int64_t now_ns, CameraFrame& f) const;
  int count() const { return p_.n; }
  void inject_stream_timeout(int cam, double seconds);
  void inject_confidence_drop(double seconds, double factor);

 private:
  CameraParams p_;
  const SimHuman& human_;
  int64_t t0_;
  std::vector<Vec3> pos_;
  std::vector<std::atomic<int64_t>> dead_until_;
  std::atomic<int64_t> conf_drop_until_{0};
  std::atomic<double> conf_factor_{1.0};
};

// ---------------------------------------------------------------------------- fusion
struct FusionParams {
  double rate_hz = 50;
  double stream_timeout_ms = 100;
  int vel_window = 10;         // fused estimates in the least-squares velocity window (~200 ms at 50 Hz)
  int cpu = -1;                // affinity (-1: none)
};

struct FusionStats {
  // histogram of fusion execution time, 10 us bins up to 50 ms
  static constexpr int kBins = 5000;
  std::array<uint64_t, kBins + 1> exec_hist{};
  uint64_t publishes = 0;
};

class CameraFusion final : public ISensorFusion {
 public:
  CameraFusion(const FusionParams& p, const SimCameraArray& cams);
  ~CameraFusion() override;
  bool start() override;
  void stop() override;
  bool latest(HumanState& out) const override { return slot_.load(out); }
  FusionStats stats() const;
  void set_shared_cpu(int cpu) { p_.cpu = cpu; }

 private:
  void loop();
  FusionParams p_;
  const SimCameraArray& cams_;
  SeqlockSlot<HumanState> slot_;
  std::atomic<bool> run_{false};
  std::thread th_;
  mutable std::mutex stats_mu_;
  FusionStats stats_;
};

}  // namespace hrc
