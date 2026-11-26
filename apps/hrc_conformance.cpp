// SPDX-License-Identifier: MIT
// Interface conformance tests against a vendor endpoint (URSim / physical controller).
// Each item: id, document clause, expected behaviour, observed behaviour, pass/fail, evidence.
// Writes runs/<ts>_conformance_<backend>/conformance.csv + manifest + MANIFEST.sha256.
//
//   hrc_conformance --backend ur_rtde --host 192.168.56.101 [--freq 500] [--backup DIR]
//
// What a pass means: the adapter and the endpoint agree on the behaviour stated in the cited
// vendor document. When the endpoint is a vendor simulator (URSim), this is a test against
// the vendor's own controller software, not against a model written by the author.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <thread>

#include "hrc/adapters.hpp"
#include "hrc/common.hpp"

using namespace hrc;
namespace fs = std::filesystem;

namespace {
struct Item {
  std::string id, clause, expected, observed, result, evidence;
};

std::string csv_esc(const std::string& s) {
  std::string o = "\"";
  for (char c : s) o += (c == '"') ? std::string("\"\"") : std::string(1, c);
  return o + "\"";
}

// Independent raw RTDE probe on a fresh connection (setup is only allowed before START).
std::string rtde_probe_outputs(const std::string& host, const std::string& vars) {
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(30004);
  inet_pton(AF_INET, host.c_str(), &a.sin_addr);
  if (::connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) { ::close(fd); return "CONNECT_FAILED"; }
  auto send_pkg = [&](uint8_t type, const std::vector<uint8_t>& p) {
    std::vector<uint8_t> b{uint8_t((p.size() + 3) >> 8), uint8_t(p.size() + 3), type};
    b.insert(b.end(), p.begin(), p.end());
    ::send(fd, b.data(), b.size(), 0);
  };
  auto recv_pkg = [&](uint8_t want, std::vector<uint8_t>& out) {
    for (int k = 0; k < 20; ++k) {
      uint8_t h[3];
      pollfd p{fd, POLLIN, 0};
      if (::poll(&p, 1, 2000) <= 0 || ::recv(fd, h, 3, MSG_WAITALL) != 3) return false;
      size_t n = static_cast<size_t>((h[0] << 8) | h[1]) - 3;
      out.resize(n);
      if (n && ::recv(fd, out.data(), n, MSG_WAITALL) != static_cast<ssize_t>(n)) return false;
      if (h[2] == want) return true;
    }
    return false;
  };
  std::vector<uint8_t> r;
  send_pkg(86, {0, 2});
  if (!recv_pkg(86, r)) { ::close(fd); return "NO_VERSION_REPLY"; }
  std::vector<uint8_t> p(8);
  double f = 10.0;
  uint64_t v;
  std::memcpy(&v, &f, 8);
  for (int i = 0; i < 8; ++i) p[static_cast<size_t>(i)] = uint8_t(v >> (56 - 8 * i));
  p.insert(p.end(), vars.begin(), vars.end());
  send_pkg(79, p);
  std::string types = recv_pkg(79, r) && !r.empty() ? std::string(r.begin() + 1, r.end()) : "NO_SETUP_REPLY";
  ::close(fd);
  return types;
}

double measure_dq(UrRtdeAdapter& ur, int joint, double qd, double secs, double period = 0.02) {
  RobotState s0, s1;
  ur.getCurrentState(s0);
  Joints cmd; cmd.n = 6;
  cmd[joint] = qd;
  const int64_t end = mono_ns() + static_cast<int64_t>(secs * 1e9);
  while (mono_ns() < end) {
    ur.streamJointVelocity(cmd, period);
    std::this_thread::sleep_for(std::chrono::duration<double>(period));
  }
  Joints z; z.n = 6;
  for (int i = 0; i < 25; ++i) { ur.streamJointVelocity(z, period); std::this_thread::sleep_for(std::chrono::duration<double>(period)); }
  ur.getCurrentState(s1);
  return s1.q[joint] - s0.q[joint];
}
}  // namespace

int main(int argc, char** argv) {
  std::string backend = "ur_rtde", host = "127.0.0.1", root = "runs";
  std::vector<std::string> backups;
  double freq = 500;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string a = argv[i], v = argv[i + 1];
    if (a == "--backend") backend = v;
    else if (a == "--host") host = v;
    else if (a == "--freq") freq = std::stod(v);
    else if (a == "--run-root") root = v;
    else if (a == "--backup") backups.push_back(v);
  }
  std::string ts = utc_iso8601(wall_ns());
  for (auto& ch : ts) if (ch == ':') ch = '-';
  fs::path dir = fs::path(root) / (ts + "_conformance_" + backend);
  fs::create_directories(dir);
  std::vector<Item> items;
  auto add = [&](Item it) {
    std::fprintf(stderr, "%-6s %-4s %s | %s\n", it.id.c_str(), it.result.c_str(), it.expected.c_str(), it.observed.c_str());
    items.push_back(std::move(it));
  };
  std::string controller_version;

  if (backend != "ur_rtde") {
    std::unique_ptr<IRobotController> r = backend == "kuka_fri" ? make_kuka_fri_adapter() : make_abb_egm_adapter();
    add({backend + "-00", "build", "adapter compiled into this binary", r ? "present" : "absent (vendor SDK/proto not supplied at build time)",
         r ? "pass" : "not_run", "no item of this checklist was executed"});
  } else {
    UrRtdeAdapter ur;
    // UR-04 first: setup probing must happen on its own connection before the adapter starts
    std::string probe = rtde_probe_outputs(host, "timestamp,hrc_not_a_variable");
    add({"UR-04", "RTDE Guide: CONTROL_PACKAGE_SETUP_OUTPUTS reply", "unknown variable reported as NOT_FOUND", probe,
         probe.find("NOT_FOUND") != std::string::npos ? "pass" : "fail", "raw probe on a separate connection"});
    ConnectionConfig cc;
    cc.host = host;
    cc.port = 30004;
    cc.options = "{\"frequency\":" + std::to_string(freq) + "}";
    Result res = ur.connect(cc);
    auto& hs = ur.handshake();
    add({"UR-01", "RTDE Guide: REQUEST_PROTOCOL_VERSION", "protocol version 2 accepted", hs.protocol_accepted ? "accepted" : "rejected",
         hs.protocol_accepted ? "pass" : "fail", ""});
    controller_version = std::to_string(hs.major) + "." + std::to_string(hs.minor) + "." + std::to_string(hs.bugfix) + "." + std::to_string(hs.build);
    add({"UR-02", "RTDE Guide: GET_URCONTROL_VERSION", "four-field version, major >= 5 (e-Series)", controller_version,
         hs.major >= 5 ? "pass" : "fail", ""});
    const std::string want = "DOUBLE,VECTOR6D,VECTOR6D,VECTOR6D,INT32,INT32,UINT32,INT32";
    add({"UR-03", "RTDE Guide: output types", want, hs.output_types, hs.output_types == want ? "pass" : "fail", "recipe " + std::to_string(hs.output_recipe)});
    add({"UR-05", "RTDE Guide: CONTROL_PACKAGE_SETUP_INPUTS", "input recipe accepted, registers 24-30 not IN_USE", hs.input_types,
         hs.input_recipe > 0 && hs.input_types.find("IN_USE") == std::string::npos ? "pass" : "fail", ""});
    if (res != Result::Ok) {
      add({"UR-00", "connect", "adapter connects and uploads hrc_follow", to_string(res), "fail", "remaining items not run"});
    } else {
      ur.dashboard("power on");
      std::this_thread::sleep_for(std::chrono::seconds(3));
      ur.dashboard("brake release");
      std::this_thread::sleep_for(std::chrono::seconds(3));
      ur.resetFault();  // re-upload the follow script after power-up
      std::this_thread::sleep_for(std::chrono::seconds(1));
      // UR-06/07 rate and validity over 10 s
      uint64_t rx0 = ur.stats().rx_packets.load(), inv0 = ur.stats().rx_invalid.load();
      std::this_thread::sleep_for(std::chrono::seconds(10));
      double rate = (ur.stats().rx_packets.load() - rx0) / 10.0;
      uint64_t inv = ur.stats().rx_invalid.load() - inv0;
      char b[160];
      std::snprintf(b, sizeof b, "%.1f Hz", rate);
      add({"UR-06", "RTDE Guide: output frequency", "state rate within 2% of " + std::to_string(static_cast<int>(freq)) + " Hz", b,
           std::fabs(rate - freq) <= 0.02 * freq ? "pass" : "fail", "10 s window"});
      add({"UR-07", "RTDE Guide: data package framing", "0 packages failing recipe/size/finite/monotonic checks", std::to_string(inv),
           inv == 0 ? "pass" : "fail", "10 s window"});
      // UR-09 velocity command executed (wrist 3, +0.2 rad/s for 2 s)
      double dq = measure_dq(ur, 5, 0.2, 2.0);
      std::snprintf(b, sizeof b, "dq = %.4f rad", dq);
      add({"UR-09", "Script Manual: speedj", "wrist 3 moves 0.40 rad +/- 15% for 0.2 rad/s x 2 s", b,
           std::fabs(dq - 0.4) <= 0.06 ? "pass" : "fail", "includes acceleration ramps"});
      // UR-12 speed slider halves the speed
      ur.setOverride(0.5);
      std::this_thread::sleep_for(std::chrono::milliseconds(200));
      double dq_half = measure_dq(ur, 5, -0.2, 2.0);
      ur.setOverride(1.0);
      std::snprintf(b, sizeof b, "dq = %.4f rad", dq_half);
      add({"UR-12", "RTDE Guide: speed_slider_mask/fraction", "same command at 50% override moves 0.20 rad +/- 20%", b,
           std::fabs(std::fabs(dq_half) - 0.2) <= 0.04 ? "pass" : "fail", ""});
      // UR-11 protective stop through the input register
      Joints cmd; cmd.n = 6; cmd[5] = 0.5;
      for (int i = 0; i < 50; ++i) { ur.streamJointVelocity(cmd, 0.02); std::this_thread::sleep_for(std::chrono::milliseconds(20)); }
      const int64_t t_stop = mono_ns();
      ur.protectiveStop(2.0);
      RobotState s;
      int64_t t_zero = 0;
      while (mono_ns() - t_stop < 2'000'000'000LL) {
        ur.getCurrentState(s);
        if (std::fabs(s.qd[5]) < 1e-3) { t_zero = mono_ns(); break; }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
      }
      std::snprintf(b, sizeof b, "stopped after %.1f ms", t_zero ? (t_zero - t_stop) * 1e-6 : -1.0);
      add({"UR-11", "Script Manual: stopj(a)", "0.5 rad/s at 2.0 rad/s^2 reaches 0 within 250 ms + 60 ms transport", b,
           t_zero && (t_zero - t_stop) < 310'000'000 ? "pass" : "fail", "theoretical ramp 250 ms"});
      // UR-10 controller-side heartbeat: stop sending, robot must stop by itself
      for (int i = 0; i < 50; ++i) { ur.streamJointVelocity(cmd, 0.02); std::this_thread::sleep_for(std::chrono::milliseconds(20)); }
      const int64_t t_silent = mono_ns();
      t_zero = 0;
      while (mono_ns() - t_silent < 2'000'000'000LL) {
        ur.getCurrentState(s);
        if (std::fabs(s.qd[5]) < 1e-3) { t_zero = mono_ns(); break; }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
      }
      std::snprintf(b, sizeof b, "stopped after %.1f ms of host silence", t_zero ? (t_zero - t_silent) * 1e-6 : -1.0);
      add({"UR-10", "hrc_follow script heartbeat (this work)", "robot stops without host commands within 64 ms + ramp 167 ms",
           b, t_zero && (t_zero - t_silent) < 300'000'000 ? "pass" : "fail", "stale_limit 8 x 8 ms; stopj at 3.0 rad/s^2"});
      std::string rm = ur.dashboard("robotmode");
      add({"UR-14", "Dashboard Server: robotmode", "dashboard answers 'Robotmode: ...'", rm, rm.rfind("Robotmode", 0) == 0 ? "pass" : "fail", ""});
      add({"UR-13", "informational", "command round-trip histogram recorded", "see manifest.json stats", "info", ""});
      write_text_file((dir / "adapter_stats.json").string(), ur.stats().to_json());
      ur.disconnect();
    }
  }

  std::ofstream f(dir / "conformance.csv");
  f << "item_id,document_clause,expected,observed,result,evidence\n";
  int pass = 0, fail = 0;
  for (auto& it : items) {
    f << it.id << "," << csv_esc(it.clause) << "," << csv_esc(it.expected) << "," << csv_esc(it.observed) << "," << it.result << ","
      << csv_esc(it.evidence) << "\n";
    pass += it.result == "pass";
    fail += it.result == "fail";
  }
  f.close();
  JsonWriter w;
  w.begin_object().kv("experiment", "conformance").kv("backend", backend).kv("endpoint", host)
      .kv("controller_version", controller_version).kv("pass", pass).kv("fail", fail)
      .kv("data_kind", "raw test outcomes written by the test program; never edited")
      .kv("end_utc", utc_iso8601(wall_ns())).end_object();
  write_text_file((dir / "manifest.json").string(), w.str());
  std::string man;
  for (auto& e : fs::directory_iterator(dir)) {
    std::string n = e.path().filename().string();
    if (n != "MANIFEST.sha256") man += sha256_file(e.path().string()) + "  " + n + "\n";
  }
  write_text_file((dir / "MANIFEST.sha256").string(), man);
  for (auto& bk : backups) {
    fs::path dst = fs::path(bk) / dir.filename();
    fs::create_directories(dst);
    for (auto& e : fs::directory_iterator(dir)) fs::copy_file(e.path(), dst / e.path().filename(), fs::copy_options::overwrite_existing);
  }
  std::fprintf(stderr, "[conformance] %d pass, %d fail -> %s\n", pass, fail, dir.c_str());
  return fail ? 1 : 0;
}
