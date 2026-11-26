// SPDX-License-Identifier: MIT
// Integration layer: Modbus TCP server (self-contained), REST API (self-contained HTTP/1.1)
// and OPC-UA server (open62541, optional). All three read one telemetry snapshot published
// by the control thread and write operator commands into atomics read by the control thread;
// none of them can reach the robot adapter.
#pragma once
#include <atomic>
#include <string>
#include <thread>

#include "hrc/run_logger.hpp"
#include "hrc/spsc.hpp"
#include "hrc/types.hpp"

namespace hrc {

struct Telemetry {
  int64_t t_ns = 0;
  Joints q, qd;
  Vec3 tcp;
  double min_sep_m = 0, h_geo = 0, override_ = 1;
  uint8_t mode = 0;
  bool learned_active = false, estimate_available = false;
  uint64_t cycle = 0;
  int task_cycles = 0;
};

enum class MissionCmd : int { None = 0, Start = 1, Pause = 2, Abort = 3 };

struct IntegrationBus {
  SeqlockSlot<Telemetry> telemetry;
  std::atomic<int> mission{static_cast<int>(MissionCmd::Start)};
  std::atomic<double> override_{1.0};
  std::atomic<uint64_t> requests{0};
};

class ModbusServer {
 public:
  ModbusServer(IntegrationBus& bus, int port, EventChannel* ev, int cpu = -1);
  ~ModbusServer();
  bool start();
  void stop();
  int port() const { return port_; }

 private:
  void loop();
  size_t handle(const uint8_t* req, size_t n, uint8_t* rep);
  IntegrationBus& bus_;
  int port_, lfd_ = -1, cpu_;
  EventChannel* ev_;
  std::atomic<bool> run_{false};
  std::thread th_;
};

class RestServer {
 public:
  RestServer(IntegrationBus& bus, int port, EventChannel* ev, int cpu = -1);
  ~RestServer();
  bool start();
  void stop();

 private:
  void loop();
  std::string handle(const std::string& method, const std::string& path, const std::string& body, int& code);
  IntegrationBus& bus_;
  int port_, lfd_ = -1, cpu_;
  EventChannel* ev_;
  std::atomic<bool> run_{false};
  std::thread th_;
};

class OpcUaServer {
 public:
  OpcUaServer(IntegrationBus& bus, int port, EventChannel* ev, int cpu = -1);
  ~OpcUaServer();
  bool available() const;  // false when built without open62541
  bool start();
  void stop();

 private:
  void loop();
  IntegrationBus& bus_;
  int port_, cpu_;
  EventChannel* ev_;
  std::atomic<bool> run_{false};
  std::thread th_;
};

// Modbus register map (Appendix A of the paper; kept here as the single source).
namespace modbus_map {
constexpr int kHrJointPos = 0;      // 0..5  int16 decidegrees
constexpr int kHrJointVel = 10;     // 10..15 int16, 0.01 rad/s
constexpr int kHrMinDist = 20;      // uint16 mm
constexpr int kHrOverride = 21;     // uint16 percent (read)
constexpr int kHrOverrideCmd = 30;  // uint16 percent (write)
constexpr int kIrPose = 100;        // 100..106 x,y,z mm (int16) + quaternion x 10000
constexpr int kNumRegs = 128;
constexpr int kCoilStatus = 0;      // 0..7
constexpr int kCoilCmd = 10;        // 10 start, 11 pause, 12 abort
constexpr int kNumCoils = 16;
}  // namespace modbus_map

}  // namespace hrc
