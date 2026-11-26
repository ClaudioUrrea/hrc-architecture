// SPDX-License-Identifier: MIT
#include <pthread.h>
#include <poll.h>
#include <sched.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstring>

#include "hrc/adapters.hpp"

namespace hrc {

namespace {
enum Op : uint8_t { kGetState = 1, kStream = 2, kStop = 3 };
#pragma pack(push, 1)
struct Req { uint8_t op; double dt; double decel; Joints qd; };
struct Rep { uint8_t res; RobotState st; };
#pragma pack(pop)
bool rd(int fd, void* p, size_t n, int ms) {
  pollfd pf{fd, POLLIN, 0};
  if (::poll(&pf, 1, ms) <= 0) return false;
  return ::recv(fd, p, n, MSG_WAITALL) == static_cast<ssize_t>(n);
}
}  // namespace

SocketTransportRobot::SocketTransportRobot(IRobotController& inner, int cpu) : inner_(inner), cpu_(cpu) {
  if (::socketpair(AF_UNIX, SOCK_STREAM, 0, fds_) != 0) throw "socketpair failed";
  th_ = std::thread([this] { serve(); });
}
SocketTransportRobot::~SocketTransportRobot() {
  run_ = false;
  ::shutdown(fds_[0], SHUT_RDWR);
  if (th_.joinable()) th_.join();
  ::close(fds_[0]);
  ::close(fds_[1]);
}

void SocketTransportRobot::serve() {
  if (cpu_ >= 0) {
    cpu_set_t s;
    CPU_ZERO(&s);
    CPU_SET(cpu_, &s);
    pthread_setaffinity_np(pthread_self(), sizeof s, &s);
  }
  Req q;
  while (run_) {
    if (!rd(fds_[1], &q, sizeof q, 100)) continue;
    Rep r{};
    switch (q.op) {
      case kGetState: r.res = static_cast<uint8_t>(inner_.getCurrentState(r.st)); break;
      case kStream: r.res = static_cast<uint8_t>(inner_.streamJointVelocity(q.qd, q.dt)); break;
      case kStop: r.res = static_cast<uint8_t>(inner_.protectiveStop(q.decel)); break;
      default: r.res = static_cast<uint8_t>(Result::InvalidArgument);
    }
    (void)::send(fds_[1], &r, sizeof r, MSG_NOSIGNAL);
  }
}

static Result call(int fd, const Req& q, Rep& r) {
  if (::send(fd, &q, sizeof q, MSG_NOSIGNAL) != static_cast<ssize_t>(sizeof q)) return Result::CommError;
  if (!rd(fd, &r, sizeof r, 10)) return Result::Timeout;
  return static_cast<Result>(r.res);
}

Result SocketTransportRobot::getCurrentState(RobotState& out) {
  Req q{}; q.op = kGetState;
  Rep r{};
  Result res = call(fds_[0], q, r);
  if (res == Result::Ok) out = r.st;
  return res;
}
Result SocketTransportRobot::streamJointVelocity(const Joints& qd, double dt) {
  Req q{}; q.op = kStream; q.qd = qd; q.dt = dt;
  Rep r{};
  return call(fds_[0], q, r);
}
Result SocketTransportRobot::protectiveStop(double d) {
  Req q{}; q.op = kStop; q.decel = d;
  Rep r{};
  return call(fds_[0], q, r);
}

}  // namespace hrc
