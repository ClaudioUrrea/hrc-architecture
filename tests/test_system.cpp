// SPDX-License-Identifier: MIT
// Integration tests: logger provenance chain, simulator, fusion, Modbus server, fault schedule.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <thread>

#include "hrc/adapters.hpp"
#include "hrc/common.hpp"
#include "hrc/faults.hpp"
#include "hrc/integration.hpp"
#include "hrc/run_logger.hpp"
#include "hrc/sim.hpp"
#include "minitest.hpp"

using namespace hrc;
namespace fs = std::filesystem;

TEST(logger_hashes_and_verified_backup) {
  fs::path root = fs::temp_directory_path() / "hrc_test_runs", bk = fs::temp_directory_path() / "hrc_test_backup";
  fs::remove_all(root);
  fs::remove_all(bk);
  write_text_file((fs::temp_directory_path() / "hrc_test_cfg.json").string(), "{\"experiment\":\"t\"}");
  RunLogger L;
  RunInfo ri;
  ri.run_root = root.string();
  ri.experiment = "unit";
  ri.config_path = (fs::temp_directory_path() / "hrc_test_cfg.json").string();
  ri.backup_dirs = {bk.string()};
  std::string dir = L.open(ri);
  EventChannel* ev = L.channel("t");
  for (uint64_t i = 0; i < 1000; ++i) { CycleRecord r{}; r.idx = i; L.push_cycle(r); }
  ev->emit(EventKind::Info, 0, 1.0, 0, "hello");
  std::this_thread::sleep_for(std::chrono::milliseconds(120));
  CHECK(L.close());
  CHECK(fs::file_size(fs::path(dir) / "cycles.bin") == 1000 * sizeof(CycleRecord));
  std::string man = read_text_file((fs::path(dir) / "MANIFEST.sha256").string());
  CHECK(man.find("cycles.bin") != std::string::npos);
  CHECK(man.find(sha256_file((fs::path(dir) / "cycles.bin").string())) != std::string::npos);
  fs::path copy = bk / fs::path(dir).filename();
  CHECK(sha256_file((copy / "cycles.bin").string()) == sha256_file((fs::path(dir) / "cycles.bin").string()));
  CHECK(read_text_file((fs::path(dir) / "events.jsonl").string()).find("hello") != std::string::npos);
  CHECK(fs::exists(root / "INDEX.csv"));
  fs::permissions(dir, fs::perms::owner_all, fs::perm_options::add);
  for (auto& e : fs::directory_iterator(dir)) fs::permissions(e.path(), fs::perms::owner_all, fs::perm_options::add);
  fs::remove_all(root);
  fs::remove_all(bk);
}

TEST(sim_robot_follows_velocity_and_stops) {
  SimRobotParams p;
  p.limits.qd_max.n = p.limits.qdd_max.n = p.limits.qmin.n = p.limits.qmax.n = 6;
  for (int i = 0; i < 6; ++i) { p.limits.qd_max[i] = 1; p.limits.qdd_max[i] = 4; p.limits.qmin[i] = -6; p.limits.qmax[i] = 6; }
  p.q0.n = 6;
  SimRobot r(p);
  CHECK(r.connect({}) == Result::Ok);
  Joints qd; qd.n = 6; qd[0] = 0.5;
  RobotState s0, s1;
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  r.getCurrentState(s0);
  for (int i = 0; i < 50; ++i) { r.streamJointVelocity(qd, 0.02); std::this_thread::sleep_for(std::chrono::milliseconds(20)); }
  r.getCurrentState(s1);
  CHECK_NEAR(s1.q[0] - s0.q[0], 0.5, 0.08);
  r.protectiveStop(3.0);
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  r.getCurrentState(s1);
  CHECK(std::fabs(s1.qd[0]) < 1e-6);
  r.inject_comm_faults(2);
  CHECK(r.getCurrentState(s1) == Result::CommError);
  CHECK(r.getCurrentState(s1) == Result::CommError);
  CHECK(r.getCurrentState(s1) == Result::Ok);
  r.disconnect();
}

TEST(fusion_publishes_and_detects_dead_stream) {
  HumanScriptParams hp;
  SimHuman h(hp);
  CameraParams cp;
  SimCameraArray cams(cp, h, mono_ns());
  FusionParams fp;
  CameraFusion f(fp, cams);
  f.start();
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  HumanState hs;
  CHECK(f.latest(hs));
  CHECK(hs.available);
  CHECK(hs.streams_alive == 6);
  CHECK(hs.mean_conf > 0.5);
  cams.inject_stream_timeout(2, 1.0);
  std::this_thread::sleep_for(std::chrono::milliseconds(250));
  f.latest(hs);
  CHECK(hs.streams_alive == 5);
  f.stop();
}

TEST(modbus_read_and_exception) {
  IntegrationBus bus;
  Telemetry t;
  t.q.n = 6;
  t.q[0] = M_PI / 2;   // 900 decidegrees
  t.min_sep_m = 0.321;
  bus.telemetry.store(t);
  ModbusServer srv(bus, 15020, nullptr);
  CHECK(srv.start());
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(15020);
  inet_pton(AF_INET, "127.0.0.1", &a.sin_addr);
  CHECK(::connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) == 0);
  uint8_t q[12] = {0, 1, 0, 0, 0, 6, 1, 3, 0, 0, 0, 21};  // FC03, address 0, 21 registers
  ::send(fd, q, sizeof q, 0);
  uint8_t r[64];
  ssize_t n = ::recv(fd, r, 51, MSG_WAITALL);
  CHECK(n == 9 + 42);
  CHECK(r[7] == 3 && r[8] == 42);
  CHECK(((r[9] << 8) | r[10]) == 900);
  CHECK(((r[9 + 40] << 8) | r[10 + 40]) == 321);
  uint8_t bad[12] = {0, 2, 0, 0, 0, 6, 1, 0x2B, 0, 0, 0, 1};  // unsupported function
  ::send(fd, bad, sizeof bad, 0);
  n = ::recv(fd, r, 9, MSG_WAITALL);
  CHECK(n == 9 && r[7] == (0x2B | 0x80) && r[8] == 1);
  uint8_t wr[12] = {0, 3, 0, 0, 0, 6, 1, 6, 0, 30, 0, 40};  // override 40 %
  ::send(fd, wr, sizeof wr, 0);
  n = ::recv(fd, r, 12, MSG_WAITALL);
  CHECK(n == 12);
  CHECK_NEAR(bus.override_.load(), 0.4, 1e-12);
  ::close(fd);
  srv.stop();
}

TEST(fault_schedule_rates) {
  FaultCampaignParams p;
  p.enabled = true;
  p.rate_tracking_loss = 10;  // per hour
  p.seed = 11;
  for (const char* arr : {"poisson", "clustered", "weibull"}) {
    p.arrival = arr;
    auto s = make_schedule(p, 3600 * 200.0);
    double rate = s.size() / 200.0;
    CHECK_NEAR(rate, 10.0, 1.5);  // same long-run rate for every arrival model
  }
}

TEST(ur_follow_script_has_controller_side_heartbeat) {
  std::string s = UrRtdeAdapter::follow_script(8, 4.0, 0.008, 3.0);
  CHECK(s.find("speedj(qd, 4, 0.008)") != std::string::npos);
  CHECK(s.find("stale < 8") != std::string::npos);
  CHECK(s.find("stopj(dec)") != std::string::npos);
}

int main() { return minitest::run_all(); }
