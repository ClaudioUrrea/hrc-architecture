// SPDX-License-Identifier: MIT
// KUKA LBR iiwa adapter over the Fast Robot Interface (FRI), Sunrise.OS 1.17.
//
// The FRI client SDK (friClientApplication.h, friLBRClient.h, friUdpConnection.h) is
// licensed by KUKA and not redistributed here. Build with -DHRC_FRI_SDK_DIR=/path/to/FRI-Client-SDK_Cpp.
// The Sunrise side runs an application that opens an FRI session in joint-position
// command mode (FRIConfiguration with setSendPeriodMilliSec(5)); the URL/port are given in
// the adapter options. Velocity commands are integrated to joint positions at the FRI
// sample time, because FRI commands positions.
//
// STATUS: written against the documented SDK API but NOT compiled or tested in the author's
// environment unless the conformance log for KUKA says otherwise.
#include "hrc/adapters.hpp"

#ifdef HRC_HAVE_FRI
#include <atomic>
#include <thread>

#include "friClientApplication.h"
#include "friLBRClient.h"
#include "friUdpConnection.h"
#include "hrc/common.hpp"

namespace hrc {
namespace {

class HrcLbrClient : public KUKA::FRI::LBRClient {
 public:
  SeqlockSlot<RobotState> state;
  SeqlockSlot<Joints> qd_cmd;
  std::atomic<bool> stop{false};
  std::atomic<double> decel{1.0};
  std::atomic<int> session{0};
  double q_cmd[7]{};
  double qd_cur[7]{};

  void onStateChange(KUKA::FRI::ESessionState, KUKA::FRI::ESessionState n) override { session = static_cast<int>(n); }
  void publish() {
    RobotState s;
    s.q.n = s.qd.n = 7;
    const double* q = robotState().getMeasuredJointPosition();
    static double qprev[7]{};
    const double dt = robotState().getSampleTime();
    for (int i = 0; i < 7; ++i) { s.q[i] = q[i]; s.qd[i] = (q[i] - qprev[i]) / dt; qprev[i] = q[i]; }
    s.t_ns = mono_ns();
    s.valid = true;
    s.seq = static_cast<uint32_t>(robotState().getTimestampNanoSec());
    state.store(s);
  }
  void monitor() override { LBRClient::monitor(); publish(); }
  void waitForCommand() override {
    LBRClient::waitForCommand();
    const double* q = robotState().getIpoJointPosition();
    for (int i = 0; i < 7; ++i) { q_cmd[i] = q[i]; qd_cur[i] = 0; }
    robotCommand().setJointPosition(q_cmd);
    publish();
  }
  void command() override {
    publish();
    const double dt = robotState().getSampleTime();
    Joints qd;
    if (!qd_cmd.load(qd)) qd.n = 7;
    for (int i = 0; i < 7; ++i) {
      double target = stop ? 0.0 : qd[i];
      double a = decel.load();
      double dv = std::max(-a * dt, std::min(a * dt, target - qd_cur[i]));
      qd_cur[i] += stop ? dv : (target - qd_cur[i]);
      q_cmd[i] += qd_cur[i] * dt;
    }
    robotCommand().setJointPosition(q_cmd);
  }
};

class KukaFriAdapter final : public IRobotController {
 public:
  const char* name() const override { return "kuka_fri"; }
  Result connect(const ConnectionConfig& c) override {
    app_ = std::make_unique<KUKA::FRI::ClientApplication>(conn_, client_);
    if (!app_->connect(c.port ? c.port : 30200, c.host.c_str())) return Result::NotConnected;
    run_ = true;
    th_ = std::thread([this] { while (run_ && app_->step()) {} connected_ = false; });
    connected_ = true;
    return Result::Ok;
  }
  Result disconnect() override {
    run_ = false;
    if (th_.joinable()) th_.join();
    if (app_) app_->disconnect();
    connected_ = false;
    return Result::Ok;
  }
  bool isConnected() const override { return connected_; }
  Result getCurrentState(RobotState& out) override { return client_.state.load(out) ? Result::Ok : Result::Timeout; }
  Result streamJointVelocity(const Joints& qd, double) override {
    if (client_.session != KUKA::FRI::COMMANDING_ACTIVE) return Result::Rejected;
    client_.stop = false;
    client_.qd_cmd.store(qd);
    return Result::Ok;
  }
  Result setOverride(double) override { return Result::Unsupported; }  // set on the Sunrise side
  Result protectiveStop(double d) override { client_.decel = d; client_.stop = true; return Result::Ok; }
  Result emergencyStop() override { return protectiveStop(5.0); }       // not safety-rated
  HealthStatus getHealthStatus() const override { HealthStatus h; h.connected = connected_; h.vendor_code = client_.session; return h; }
  Result moveJoint(const Joints&, double) override { return Result::Unsupported; }
  Limits getKinematicLimits() const override {
    Limits l;
    const double qmax[7] = {2.967, 2.094, 2.967, 2.094, 2.967, 2.094, 3.054};   // LBR iiwa 7 R800 data sheet
    const double vmax[7] = {1.710, 1.710, 1.745, 2.269, 2.443, 3.142, 3.142};
    for (auto* j : {&l.qmin, &l.qmax, &l.qd_max, &l.qdd_max}) j->n = 7;
    for (int i = 0; i < 7; ++i) { l.qmin[i] = -qmax[i]; l.qmax[i] = qmax[i]; l.qd_max[i] = vmax[i]; l.qdd_max[i] = 5.0; }
    return l;
  }
  Result resetFault() override { client_.stop = false; return Result::Ok; }

 private:
  KUKA::FRI::UdpConnection conn_;
  HrcLbrClient client_;
  std::unique_ptr<KUKA::FRI::ClientApplication> app_;
  std::thread th_;
  std::atomic<bool> run_{false}, connected_{false};
};
}  // namespace

std::unique_ptr<IRobotController> make_kuka_fri_adapter() { return std::make_unique<KukaFriAdapter>(); }
}  // namespace hrc

#else
namespace hrc {
std::unique_ptr<IRobotController> make_kuka_fri_adapter() { return nullptr; }
}  // namespace hrc
#endif
