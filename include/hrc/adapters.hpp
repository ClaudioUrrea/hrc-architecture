// SPDX-License-Identifier: MIT
// Vendor adapters. Each implements IRobotController against one vendor interface.
//   UrRtdeAdapter   Universal Robots e-Series: RTDE (TCP 30004) + URScript (TCP 30002) +
//                   Dashboard (TCP 29999). Self-contained, no vendor library.
//   KukaFriAdapter  KUKA Sunrise FRI. Requires the KUKA FRI client SDK (not redistributable);
//                   built only when -DHRC_FRI_SDK_DIR=... is given.
//   AbbEgmAdapter   ABB OmniCore: Externally Guided Motion (UDP, protobuf egm.proto shipped
//                   with RobotWare) for the cyclic path + Robot Web Services 2.0 (HTTPS) for
//                   supervisory calls. Built only when -DHRC_EGM_PROTO=... is given.
//   MockRobot       deterministic in-process double used by unit tests.
#pragma once
#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "hrc/interfaces.hpp"
#include "hrc/spsc.hpp"

namespace hrc {

class Json;

// ---------------------------------------------------------------------------- statistics shared by adapters
struct AdapterStats {
  std::atomic<uint64_t> rx_packets{0}, rx_invalid{0}, tx_packets{0}, tx_errors{0};
  // command round trip (host write -> controller echo seen by host), 10 us bins to 100 ms
  static constexpr int kBins = 10000;
  std::array<std::atomic<uint32_t>, kBins + 1> rtt_hist{};
  // state inter-arrival, 10 us bins to 100 ms
  std::array<std::atomic<uint32_t>, kBins + 1> rx_interval_hist{};
  std::string to_json() const;
};

// ---------------------------------------------------------------------------- UR RTDE
class UrRtdeAdapter final : public IRobotController {
 public:
  UrRtdeAdapter();
  ~UrRtdeAdapter() override;
  const char* name() const override { return "ur_rtde"; }
  Result connect(const ConnectionConfig& cfg) override;
  Result disconnect() override;
  bool isConnected() const override { return connected_.load(); }
  Result getCurrentState(RobotState& out) override;
  Result streamJointVelocity(const Joints& qd, double dt_s) override;
  Result setOverride(double factor) override;
  Result protectiveStop(double decel) override;
  Result emergencyStop() override;
  HealthStatus getHealthStatus() const override;
  Result moveJoint(const Joints& target, double vel) override;
  Limits getKinematicLimits() const override;
  Result resetFault() override;

  // Conformance helpers (used by apps/hrc_conformance; not on the cyclic path).
  struct Handshake {
    bool protocol_accepted = false;
    uint32_t major = 0, minor = 0, bugfix = 0, build = 0;
    std::string output_types, input_types;
    int output_recipe = -1, input_recipe = -1;
  };
  const Handshake& handshake() const { return hs_; }
  std::string dashboard(const std::string& cmd, int timeout_ms = 2000);
  // Raw request used by conformance tests (e.g. NOT_FOUND on an unknown variable).
  std::string setup_outputs_probe(const std::string& vars, double freq);
  const AdapterStats& stats() const { return stats_; }
  static std::string follow_script(int stale_limit, double acc, double tstep, double dec);
  int32_t robot_mode() const { return robot_mode_.load(); }
  int32_t safety_mode() const { return safety_mode_.load(); }
  uint32_t runtime_state() const { return runtime_state_.load(); }
  double controller_timestamp() const { return ctrl_ts_.load(); }

 private:
  bool send_pkg(uint8_t type, const std::vector<uint8_t>& payload);
  bool recv_pkg(uint8_t& type, std::vector<uint8_t>& payload, int timeout_ms);
  bool request(uint8_t type, const std::vector<uint8_t>& payload, std::vector<uint8_t>& reply, int timeout_ms);
  bool upload_script(const std::string& script);
  void rx_loop();
  Result send_inputs(int32_t mode, const Joints& qd, double decel);

  int fd_ = -1;
  std::string host_;
  int script_port_ = 30002, dash_port_ = 29999;
  double freq_ = 500, acc_ = 4.0, dec_default_ = 3.0, tstep_ = 0.008;
  int stale_limit_ = 8;
  Handshake hs_;
  std::vector<std::string> out_types_;
  std::atomic<bool> connected_{false}, run_{false};
  std::thread rx_;
  std::mutex tx_mu_;
  SeqlockSlot<RobotState> state_;
  std::atomic<bool> last_invalid_{false};
  std::atomic<int32_t> robot_mode_{-1}, safety_mode_{-1};
  std::atomic<uint32_t> runtime_state_{0};
  std::atomic<double> ctrl_ts_{0};
  std::atomic<int32_t> counter_{0};
  std::atomic<double> pending_override_{-1};
  std::array<std::atomic<int64_t>, 256> sent_at_{};  // counter % 256 -> send time
  AdapterStats stats_;
  int64_t last_rx_ns_ = 0;
  double last_ts_ = -1;
};

// ---------------------------------------------------------------------------- KUKA FRI
std::unique_ptr<IRobotController> make_kuka_fri_adapter();   // nullptr if not built with the SDK
// ---------------------------------------------------------------------------- ABB EGM + RWS
std::unique_ptr<IRobotController> make_abb_egm_adapter();    // nullptr if not built with egm.proto

// ---------------------------------------------------------------------------- mock
class MockRobot final : public IRobotController {
 public:
  explicit MockRobot(int dof = 6) { st_.q.n = st_.qd.n = dof; st_.valid = true; }
  const char* name() const override { return "mock"; }
  Result connect(const ConnectionConfig&) override { connected_ = true; return Result::Ok; }
  Result disconnect() override { connected_ = false; return Result::Ok; }
  bool isConnected() const override { return connected_; }
  Result getCurrentState(RobotState& out) override { out = st_; return connected_ ? Result::Ok : Result::NotConnected; }
  Result streamJointVelocity(const Joints& qd, double dt) override {
    last_qd = qd;
    for (int i = 0; i < qd.n; ++i) st_.q[i] += qd[i] * dt;
    st_.qd = qd;
    ++stream_calls;
    return Result::Ok;
  }
  Result setOverride(double f) override { return (f < 0 || f > 1) ? Result::InvalidArgument : Result::Ok; }
  Result protectiveStop(double) override { ++stops; st_.qd = Joints{}; st_.qd.n = st_.q.n; return Result::Ok; }
  Result emergencyStop() override { ++estops; return Result::Ok; }
  HealthStatus getHealthStatus() const override { HealthStatus h; h.connected = connected_; return h; }
  Result moveJoint(const Joints& t, double) override { st_.q = t; return Result::Ok; }
  Limits getKinematicLimits() const override { return limits; }
  Result resetFault() override { return Result::Ok; }
  RobotState& state() { return st_; }
  Joints last_qd;
  int stream_calls = 0, stops = 0, estops = 0;
  Limits limits;

 private:
  RobotState st_;
  bool connected_ = false;
};

// ---------------------------------------------------------------------------- socket transport (ablation A1)
// Forwards the cyclic calls of an adapter through a UNIX-domain socket pair to a server
// thread, replacing the in-process seqlock path. Used only to measure transport cost.
class SocketTransportRobot final : public IRobotController {
 public:
  explicit SocketTransportRobot(IRobotController& inner, int server_cpu = -1);
  ~SocketTransportRobot() override;
  const char* name() const override { return "socket_transport"; }
  Result connect(const ConnectionConfig& c) override { return inner_.connect(c); }
  Result disconnect() override { return inner_.disconnect(); }
  bool isConnected() const override { return inner_.isConnected(); }
  Result getCurrentState(RobotState& out) override;
  Result streamJointVelocity(const Joints& qd, double dt) override;
  Result setOverride(double f) override { return inner_.setOverride(f); }
  Result protectiveStop(double d) override;
  Result emergencyStop() override { return inner_.emergencyStop(); }
  HealthStatus getHealthStatus() const override { return inner_.getHealthStatus(); }
  Result moveJoint(const Joints& t, double v) override { return inner_.moveJoint(t, v); }
  Limits getKinematicLimits() const override { return inner_.getKinematicLimits(); }
  Result resetFault() override { return inner_.resetFault(); }

 private:
  void serve();
  IRobotController& inner_;
  int fds_[2] = {-1, -1};
  std::atomic<bool> run_{true};
  std::thread th_;
  int cpu_;
};

}  // namespace hrc
