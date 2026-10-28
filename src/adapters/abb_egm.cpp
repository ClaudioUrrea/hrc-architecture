// SPDX-License-Identifier: MIT
// ABB OmniCore adapter: Externally Guided Motion (EGM) for the cyclic path, Robot Web
// Services 2.0 for supervisory calls (speed ratio, RAPID stop/start).
//
// EGM messages are defined by egm.proto, which ships with RobotWare and is not redistributed.
// Build with -DHRC_EGM_PROTO=/path/to/egm.proto (protobuf compiler required). The RAPID side
// runs EGMActJoint/EGMRunJoint with a UdpUc device pointing at this host; the controller is
// the EGM client and sends EgmRobot messages every 4 ms, to which this adapter answers with
// EgmSensor messages carrying a joint-velocity reference (speedRef) and position reference.
//
// RWS endpoint paths are read from the adapter options because they differ between RWS 1.0
// (IRC5) and RWS 2.0 (OmniCore); the defaults are those of RWS 2.0 and must be confirmed
// by the conformance checklist tests/conformance/abb_rws_checklist.json before use.
//
// STATUS: written against the documented interfaces but NOT compiled or tested in the
// author's environment unless the conformance log for ABB says otherwise.
#include "hrc/adapters.hpp"

#ifdef HRC_HAVE_EGM
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cmath>

#include "egm.pb.h"
#include "hrc/common.hpp"

namespace hrc {
namespace {

class AbbEgmAdapter final : public IRobotController {
 public:
  const char* name() const override { return "abb_egm"; }
  Result connect(const ConnectionConfig& c) override {
    fd_ = ::socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(static_cast<uint16_t>(c.port ? c.port : 6510));
    a.sin_addr.s_addr = INADDR_ANY;
    if (fd_ < 0 || ::bind(fd_, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) return Result::NotConnected;
    run_ = true;
    th_ = std::thread([this] { loop(); });
    connected_ = true;
    return Result::Ok;
  }
  Result disconnect() override {
    run_ = false;
    if (th_.joinable()) th_.join();
    if (fd_ >= 0) ::close(fd_);
    fd_ = -1;
    connected_ = false;
    return Result::Ok;
  }
  bool isConnected() const override { return connected_; }
  Result getCurrentState(RobotState& o) override { return state_.load(o) ? Result::Ok : Result::Timeout; }
  Result streamJointVelocity(const Joints& qd, double) override { stop_ = false; cmd_.store(qd); return Result::Ok; }
  Result setOverride(double) override { return Result::Unsupported; }  // via RWS speed ratio (see options)
  Result protectiveStop(double) override { stop_ = true; return Result::Ok; }
  Result emergencyStop() override { stop_ = true; return Result::Ok; }  // not safety-rated
  HealthStatus getHealthStatus() const override { HealthStatus h; h.connected = connected_; return h; }
  Result moveJoint(const Joints&, double) override { return Result::Unsupported; }
  Limits getKinematicLimits() const override {
    Limits l;
    for (auto* j : {&l.qmin, &l.qmax, &l.qd_max, &l.qdd_max}) j->n = 7;
    for (int i = 0; i < 7; ++i) { l.qmin[i] = -2.9; l.qmax[i] = 2.9; l.qd_max[i] = 3.14; l.qdd_max[i] = 5; }  // verify against IRB 14000 product spec
    return l;
  }
  Result resetFault() override { stop_ = false; return Result::Ok; }

 private:
  void loop() {
    char buf[1400];
    sockaddr_in from{};
    socklen_t fl = sizeof from;
    uint32_t seq = 0;
    while (run_) {
      pollfd p{fd_, POLLIN, 0};
      if (::poll(&p, 1, 100) <= 0) continue;
      ssize_t n = ::recvfrom(fd_, buf, sizeof buf, 0, reinterpret_cast<sockaddr*>(&from), &fl);
      if (n <= 0) continue;
      abb::egm::EgmRobot r;
      if (!r.ParseFromArray(buf, static_cast<int>(n))) continue;
      RobotState s;
      s.t_ns = mono_ns();
      s.valid = true;
      s.seq = r.header().seqno();
      const auto& j = r.feedback().joints().joints();
      s.q.n = s.qd.n = std::min(7, j.size());
      for (int i = 0; i < s.q.n; ++i) s.q[i] = j.Get(i) * M_PI / 180.0;  // EGM joints in degrees
      state_.store(s);
      Joints qd;
      if (!cmd_.load(qd)) qd.n = s.q.n;
      abb::egm::EgmSensor m;
      auto* h = m.mutable_header();
      h->set_seqno(++seq);
      h->set_tm(static_cast<uint32_t>(mono_ns() / 1000000));
      h->set_mtype(abb::egm::EgmHeader_MessageType_MSGTYPE_CORRECTION);
      auto* pj = m.mutable_planned()->mutable_joints();
      auto* sj = m.mutable_speedref()->mutable_joints();
      for (int i = 0; i < s.q.n; ++i) {
        double v = stop_ ? 0.0 : qd[i];
        pj->add_joints((s.q[i] + v * 0.004) * 180.0 / M_PI);
        sj->add_joints(v * 180.0 / M_PI);
      }
      std::string out;
      m.SerializeToString(&out);
      ::sendto(fd_, out.data(), out.size(), 0, reinterpret_cast<sockaddr*>(&from), fl);
    }
  }
  int fd_ = -1;
  std::thread th_;
  std::atomic<bool> run_{false}, connected_{false}, stop_{false};
  SeqlockSlot<RobotState> state_;
  SeqlockSlot<Joints> cmd_;
};
}  // namespace

std::unique_ptr<IRobotController> make_abb_egm_adapter() { return std::make_unique<AbbEgmAdapter>(); }
}  // namespace hrc

#else
namespace hrc {
std::unique_ptr<IRobotController> make_abb_egm_adapter() { return nullptr; }
}  // namespace hrc
#endif
