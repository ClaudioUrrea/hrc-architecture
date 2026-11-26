// SPDX-License-Identifier: MIT
// Universal Robots e-Series adapter, implemented directly against the public
// "Real-Time Data Exchange (RTDE) Guide" (protocol version 2) and the e-Series Script Manual.
//
// Cyclic path:  host --RTDE input recipe (TCP 30004)--> controller registers
//               controller URScript `hrc_follow` reads the registers every 8 ms and calls
//               speedj(); if the host counter stops changing for `stale_limit` iterations,
//               the script itself calls stopj() (controller-side heartbeat, independent of
//               the host).
//               controller --RTDE output recipe--> host (state at `frequency` Hz)
#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cmath>
#include <cstring>
#include <sstream>

#include "hrc/adapters.hpp"
#include "hrc/common.hpp"

namespace hrc {

namespace {
enum : uint8_t {
  RTDE_REQUEST_PROTOCOL_VERSION = 86,      // 'V'
  RTDE_GET_URCONTROL_VERSION = 118,        // 'v'
  RTDE_TEXT_MESSAGE = 77,                  // 'M'
  RTDE_DATA_PACKAGE = 85,                  // 'U'
  RTDE_CONTROL_PACKAGE_SETUP_OUTPUTS = 79, // 'O'
  RTDE_CONTROL_PACKAGE_SETUP_INPUTS = 73,  // 'I'
  RTDE_CONTROL_PACKAGE_START = 83,         // 'S'
  RTDE_CONTROL_PACKAGE_PAUSE = 80,         // 'P'
};

const char* kOutputs =
    "timestamp,actual_q,actual_qd,actual_TCP_pose,robot_mode,safety_mode,runtime_state,output_int_register_24";
// Registers 24..47 are reserved for external RTDE clients (0..23 belong to fieldbus/PLC use).
const char* kInputs =
    "input_int_register_24,input_int_register_25,input_double_register_24,input_double_register_25,"
    "input_double_register_26,input_double_register_27,input_double_register_28,input_double_register_29,"
    "input_double_register_30,speed_slider_mask,speed_slider_fraction";

void put_u16(std::vector<uint8_t>& b, uint16_t v) { b.push_back(uint8_t(v >> 8)); b.push_back(uint8_t(v)); }
void put_u32(std::vector<uint8_t>& b, uint32_t v) { for (int i = 3; i >= 0; --i) b.push_back(uint8_t(v >> (8 * i))); }
void put_i32(std::vector<uint8_t>& b, int32_t v) { put_u32(b, static_cast<uint32_t>(v)); }
void put_f64(std::vector<uint8_t>& b, double d) {
  uint64_t v;
  std::memcpy(&v, &d, 8);
  for (int i = 7; i >= 0; --i) b.push_back(uint8_t(v >> (8 * i)));
}
uint32_t get_u32(const uint8_t* p) { return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3]; }
uint64_t get_u64(const uint8_t* p) { return (uint64_t(get_u32(p)) << 32) | get_u32(p + 4); }
double get_f64(const uint8_t* p) { uint64_t v = get_u64(p); double d; std::memcpy(&d, &v, 8); return d; }

std::vector<std::string> split(const std::string& s, char c) {
  std::vector<std::string> o;
  std::stringstream ss(s);
  std::string t;
  while (std::getline(ss, t, c)) o.push_back(t);
  return o;
}
size_t type_size(const std::string& t) {
  if (t == "BOOL" || t == "UINT8") return 1;
  if (t == "UINT32" || t == "INT32") return 4;
  if (t == "UINT64" || t == "DOUBLE") return 8;
  if (t == "VECTOR3D") return 24;
  if (t == "VECTOR6D") return 48;
  if (t == "VECTOR6INT32" || t == "VECTOR6UINT32") return 24;
  return 0;
}

int tcp_connect(const std::string& host, int port, int timeout_ms) {
  addrinfo hints{}, *res = nullptr;
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &res) != 0 || !res) return -1;
  int fd = ::socket(res->ai_family, res->ai_socktype, 0);
  if (fd < 0) { freeaddrinfo(res); return -1; }
  timeval tv{timeout_ms / 1000, (timeout_ms % 1000) * 1000};
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
  if (::connect(fd, res->ai_addr, res->ai_addrlen) != 0) { ::close(fd); freeaddrinfo(res); return -1; }
  freeaddrinfo(res);
  int one = 1;
  setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
  return fd;
}

bool read_exact(int fd, uint8_t* p, size_t n, int timeout_ms) {
  size_t got = 0;
  while (got < n) {
    pollfd pfd{fd, POLLIN, 0};
    int r = ::poll(&pfd, 1, timeout_ms);
    if (r <= 0) return false;
    ssize_t k = ::recv(fd, p + got, n - got, 0);
    if (k <= 0) return false;
    got += static_cast<size_t>(k);
  }
  return true;
}
}  // namespace

std::string AdapterStats::to_json() const {
  auto hist = [](const std::array<std::atomic<uint32_t>, kBins + 1>& h) {
    std::string o = "{\"bin_us\":10,\"counts_sparse\":{";
    bool first = true;
    for (int i = 0; i <= kBins; ++i) {
      uint32_t c = h[static_cast<size_t>(i)].load();
      if (!c) continue;
      o += (first ? "" : ",") + std::string("\"") + std::to_string(i) + "\":" + std::to_string(c);
      first = false;
    }
    return o + "}}";
  };
  return "{\"rx_packets\":" + std::to_string(rx_packets.load()) + ",\"rx_invalid\":" + std::to_string(rx_invalid.load()) +
         ",\"tx_packets\":" + std::to_string(tx_packets.load()) + ",\"tx_errors\":" + std::to_string(tx_errors.load()) +
         ",\"command_rtt\":" + hist(rtt_hist) + ",\"state_interarrival\":" + hist(rx_interval_hist) + "}";
}

UrRtdeAdapter::UrRtdeAdapter() = default;
UrRtdeAdapter::~UrRtdeAdapter() { disconnect(); }

std::string UrRtdeAdapter::follow_script(int stale_limit, double acc, double tstep, double dec) {
  std::ostringstream s;
  s << "def hrc_follow():\n"
       "  textmsg(\"hrc_follow started\")\n"
       "  last = read_input_integer_register(25)\n"
       "  stale = 0\n"
       "  while (True):\n"
       "    mode = read_input_integer_register(24)\n"
       "    cnt = read_input_integer_register(25)\n"
       "    if (cnt == last):\n"
       "      stale = stale + 1\n"
       "    else:\n"
       "      stale = 0\n"
       "      last = cnt\n"
       "    end\n"
       "    write_output_integer_register(24, cnt)\n"
       "    if (mode == 1 and stale < " << stale_limit << "):\n"
       "      qd = [read_input_float_register(24), read_input_float_register(25), read_input_float_register(26), "
       "read_input_float_register(27), read_input_float_register(28), read_input_float_register(29)]\n"
       "      speedj(qd, " << acc << ", " << tstep << ")\n"
       "    else:\n"
       "      dec = read_input_float_register(30)\n"
       "      if (dec <= 0):\n"
       "        dec = " << dec << "\n"
       "      end\n"
       "      stopj(dec)\n"
       "      sync()\n"
       "    end\n"
       "  end\n"
       "end\n";
  return s.str();
}

bool UrRtdeAdapter::send_pkg(uint8_t type, const std::vector<uint8_t>& payload) {
  std::vector<uint8_t> b;
  b.reserve(payload.size() + 3);
  put_u16(b, static_cast<uint16_t>(payload.size() + 3));
  b.push_back(type);
  b.insert(b.end(), payload.begin(), payload.end());
  ssize_t w = ::send(fd_, b.data(), b.size(), MSG_NOSIGNAL);
  bool ok = w == static_cast<ssize_t>(b.size());
  if (ok) stats_.tx_packets++; else stats_.tx_errors++;
  return ok;
}

bool UrRtdeAdapter::recv_pkg(uint8_t& type, std::vector<uint8_t>& payload, int timeout_ms) {
  uint8_t h[3];
  if (!read_exact(fd_, h, 3, timeout_ms)) return false;
  uint16_t size = static_cast<uint16_t>((h[0] << 8) | h[1]);
  if (size < 3) return false;
  type = h[2];
  payload.resize(size - 3u);
  return payload.empty() || read_exact(fd_, payload.data(), payload.size(), timeout_ms);
}

bool UrRtdeAdapter::request(uint8_t type, const std::vector<uint8_t>& payload, std::vector<uint8_t>& reply,
                            int timeout_ms) {
  if (!send_pkg(type, payload)) return false;
  int64_t deadline = mono_ns() + timeout_ms * 1000000LL;
  uint8_t t;
  while (mono_ns() < deadline) {
    if (!recv_pkg(t, reply, timeout_ms)) return false;
    if (t == type) return true;  // other packages (text messages) are skipped
  }
  return false;
}

std::string UrRtdeAdapter::setup_outputs_probe(const std::string& vars, double freq) {
  std::vector<uint8_t> p, r;
  put_f64(p, freq);
  p.insert(p.end(), vars.begin(), vars.end());
  if (!request(RTDE_CONTROL_PACKAGE_SETUP_OUTPUTS, p, r, 2000) || r.empty()) return "";
  return std::string(r.begin() + 1, r.end());
}

bool UrRtdeAdapter::upload_script(const std::string& script) {
  int fd = tcp_connect(host_, script_port_, 2000);
  if (fd < 0) return false;
  ssize_t w = ::send(fd, script.data(), script.size(), MSG_NOSIGNAL);
  ::close(fd);
  return w == static_cast<ssize_t>(script.size());
}

std::string UrRtdeAdapter::dashboard(const std::string& cmd, int timeout_ms) {
  int fd = tcp_connect(host_, dash_port_, timeout_ms);
  if (fd < 0) return "";
  char buf[512];
  pollfd pfd{fd, POLLIN, 0};
  if (::poll(&pfd, 1, timeout_ms) > 0) (void)::recv(fd, buf, sizeof buf, 0);  // welcome banner
  std::string line = cmd + "\n";
  (void)::send(fd, line.data(), line.size(), MSG_NOSIGNAL);
  std::string out;
  if (::poll(&pfd, 1, timeout_ms) > 0) {
    ssize_t k = ::recv(fd, buf, sizeof buf - 1, 0);
    if (k > 0) out.assign(buf, static_cast<size_t>(k));
  }
  ::close(fd);
  while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) out.pop_back();
  return out;
}

Result UrRtdeAdapter::connect(const ConnectionConfig& cfg) {
  host_ = cfg.host;
  if (!cfg.options.empty()) {
    Json o = Json::parse(cfg.options);
    freq_ = o["frequency"].num(freq_);
    script_port_ = static_cast<int>(o["script_port"].i64(script_port_));
    dash_port_ = static_cast<int>(o["dashboard_port"].i64(dash_port_));
    acc_ = o["accel"].num(acc_);
    dec_default_ = o["decel_default"].num(dec_default_);
    tstep_ = o["speedj_t"].num(tstep_);
    stale_limit_ = static_cast<int>(o["stale_limit"].i64(stale_limit_));
  }
  fd_ = tcp_connect(host_, cfg.port ? cfg.port : 30004, cfg.timeout_ms > 0 ? cfg.timeout_ms : 2000);
  if (fd_ < 0) return Result::NotConnected;
  std::vector<uint8_t> p, r;
  put_u16(p, 2);
  if (!request(RTDE_REQUEST_PROTOCOL_VERSION, p, r, 2000) || r.empty() || r[0] != 1) { disconnect(); return Result::Rejected; }
  hs_.protocol_accepted = true;
  if (request(RTDE_GET_URCONTROL_VERSION, {}, r, 2000) && r.size() >= 16) {
    hs_.major = get_u32(&r[0]); hs_.minor = get_u32(&r[4]); hs_.bugfix = get_u32(&r[8]); hs_.build = get_u32(&r[12]);
  }
  p.clear();
  put_f64(p, freq_);
  p.insert(p.end(), kOutputs, kOutputs + std::strlen(kOutputs));
  if (!request(RTDE_CONTROL_PACKAGE_SETUP_OUTPUTS, p, r, 2000) || r.size() < 2) { disconnect(); return Result::Rejected; }
  hs_.output_recipe = r[0];
  hs_.output_types.assign(r.begin() + 1, r.end());
  out_types_ = split(hs_.output_types, ',');
  for (auto& t : out_types_) if (type_size(t) == 0) { disconnect(); return Result::Rejected; }  // NOT_FOUND etc.
  p.assign(kInputs, kInputs + std::strlen(kInputs));
  if (!request(RTDE_CONTROL_PACKAGE_SETUP_INPUTS, p, r, 2000) || r.size() < 2) { disconnect(); return Result::Rejected; }
  hs_.input_recipe = r[0];
  hs_.input_types.assign(r.begin() + 1, r.end());
  if (hs_.input_types.find("IN_USE") != std::string::npos || hs_.input_types.find("NOT_FOUND") != std::string::npos) {
    disconnect();
    return Result::Rejected;
  }
  if (!request(RTDE_CONTROL_PACKAGE_START, {}, r, 2000) || r.empty() || r[0] != 1) { disconnect(); return Result::Rejected; }
  connected_ = run_ = true;
  // zero the inputs before the script starts reading them
  Joints z; z.n = 6;
  send_inputs(0, z, dec_default_);
  rx_ = std::thread([this] { rx_loop(); });
  if (!upload_script(follow_script(stale_limit_, acc_, tstep_, dec_default_))) return Result::CommError;
  return Result::Ok;
}

Result UrRtdeAdapter::disconnect() {
  run_ = false;
  if (fd_ >= 0) {
    std::vector<uint8_t> r;
    { std::lock_guard<std::mutex> lk(tx_mu_); send_pkg(RTDE_CONTROL_PACKAGE_PAUSE, {}); }
    ::shutdown(fd_, SHUT_RDWR);
  }
  if (rx_.joinable()) rx_.join();
  if (fd_ >= 0) ::close(fd_);
  fd_ = -1;
  connected_ = false;
  return Result::Ok;
}

void UrRtdeAdapter::rx_loop() {
  std::vector<uint8_t> pl;
  uint8_t type;
  while (run_) {
    if (!recv_pkg(type, pl, 200)) {
      if (!run_) break;
      continue;  // timeout: partition detection is the supervisor's job (state age)
    }
    const int64_t now = mono_ns();
    if (type != RTDE_DATA_PACKAGE) continue;
    stats_.rx_packets++;
    // ---- validation: recipe id, size, finiteness, monotonic timestamp, joint range
    bool ok = !pl.empty() && pl[0] == hs_.output_recipe;
    size_t need = 1;
    for (auto& t : out_types_) need += type_size(t);
    ok = ok && pl.size() == need;
    RobotState s;
    s.q.n = s.qd.n = 6;
    int32_t rmode = -1, smode = -1, echo = 0;
    uint32_t rstate = 0;
    double ts = 0;
    if (ok) {
      const uint8_t* p = &pl[1];
      ts = get_f64(p); p += 8;
      for (int i = 0; i < 6; ++i) s.q[i] = get_f64(p + 8 * i);
      p += 48;
      for (int i = 0; i < 6; ++i) s.qd[i] = get_f64(p + 8 * i);
      p += 48;
      s.tcp.p = {get_f64(p), get_f64(p + 8), get_f64(p + 16)};
      p += 48;
      rmode = static_cast<int32_t>(get_u32(p)); p += 4;
      smode = static_cast<int32_t>(get_u32(p)); p += 4;
      rstate = get_u32(p); p += 4;
      echo = static_cast<int32_t>(get_u32(p));
      for (int i = 0; i < 6 && ok; ++i) ok = std::isfinite(s.q[i]) && std::isfinite(s.qd[i]) && std::fabs(s.q[i]) < 2 * M_PI + 0.1;
      ok = ok && std::isfinite(ts) && ts >= last_ts_;
    }
    if (!ok) {
      stats_.rx_invalid++;
      last_invalid_ = true;
      continue;
    }
    last_invalid_ = false;
    if (last_rx_ns_) {
      int64_t d = (now - last_rx_ns_) / 10000;
      stats_.rx_interval_hist[static_cast<size_t>(std::min<int64_t>(AdapterStats::kBins, std::max<int64_t>(0, d)))]++;
    }
    last_rx_ns_ = now;
    last_ts_ = ts;
    // command round trip: the script echoes the counter it last read
    int64_t sent = sent_at_[static_cast<size_t>(echo & 0xff)].exchange(0);
    if (sent > 0) {
      int64_t d = (now - sent) / 10000;
      stats_.rtt_hist[static_cast<size_t>(std::min<int64_t>(AdapterStats::kBins, std::max<int64_t>(0, d)))]++;
    }
    s.t_ns = now;
    s.valid = true;
    s.seq = static_cast<uint32_t>(stats_.rx_packets.load());
    s.status_bits = (smode == 3 ? static_cast<uint32_t>(kStatusProtectiveStop) : 0u) | ((smode == 6 || smode == 7) ? static_cast<uint32_t>(kStatusEmergencyStop) : 0u) |
                    (rstate == 2 ? static_cast<uint32_t>(kStatusProgramRunning) : 0u);
    robot_mode_ = rmode;
    safety_mode_ = smode;
    runtime_state_ = rstate;
    ctrl_ts_ = ts;
    state_.store(s);
  }
}

Result UrRtdeAdapter::send_inputs(int32_t mode, const Joints& qd, double decel) {
  if (fd_ < 0) return Result::NotConnected;
  std::vector<uint8_t> p;
  p.reserve(1 + 4 + 4 + 7 * 8 + 4 + 8);
  p.push_back(static_cast<uint8_t>(hs_.input_recipe));
  const int32_t c = counter_.fetch_add(1) + 1;
  put_i32(p, mode);
  put_i32(p, c);
  for (int i = 0; i < 6; ++i) put_f64(p, qd[i]);
  put_f64(p, decel);
  double ov = pending_override_.exchange(-1);
  put_u32(p, ov >= 0 ? 1u : 0u);
  put_f64(p, ov >= 0 ? ov : 0.0);
  sent_at_[static_cast<size_t>(c & 0xff)] = mono_ns();
  std::lock_guard<std::mutex> lk(tx_mu_);
  return send_pkg(RTDE_DATA_PACKAGE, p) ? Result::Ok : Result::CommError;
}

Result UrRtdeAdapter::getCurrentState(RobotState& out) {
  if (!connected_) return Result::NotConnected;
  if (last_invalid_.exchange(false)) return Result::CommError;
  return state_.load(out) ? Result::Ok : Result::Timeout;
}
Result UrRtdeAdapter::streamJointVelocity(const Joints& qd, double) { return send_inputs(1, qd, 0.0); }
Result UrRtdeAdapter::setOverride(double f) {
  if (f < 0 || f > 1) return Result::InvalidArgument;
  pending_override_ = f;
  return Result::Ok;
}
Result UrRtdeAdapter::protectiveStop(double decel) {
  Joints z; z.n = 6;
  return send_inputs(2, z, decel);
}
Result UrRtdeAdapter::emergencyStop() {
  // NOT a safety-rated emergency stop: RTDE has no safety channel. Stops motion and the program.
  protectiveStop(dec_default_ * 2);
  return dashboard("stop").empty() ? Result::CommError : Result::Ok;
}
HealthStatus UrRtdeAdapter::getHealthStatus() const {
  HealthStatus h;
  h.connected = connected_;
  h.vendor_code = safety_mode_.load();
  RobotState s;
  if (state_.load(s)) { h.last_rx_ns = s.t_ns; h.status_bits = s.status_bits; }
  return h;
}
Result UrRtdeAdapter::moveJoint(const Joints&, double) { return Result::Unsupported; }  // streaming mode only
Limits UrRtdeAdapter::getKinematicLimits() const {
  Limits l;
  for (auto* j : {&l.qmin, &l.qmax, &l.qd_max, &l.qdd_max}) j->n = 6;
  for (int i = 0; i < 6; ++i) {
    l.qmin[i] = -2 * M_PI; l.qmax[i] = 2 * M_PI;
    l.qd_max[i] = i < 2 ? M_PI : M_PI;   // e-Series joint speed limit 180 deg/s
    l.qdd_max[i] = 8.0;
  }
  return l;
}
Result UrRtdeAdapter::resetFault() {
  dashboard("unlock protective stop");
  dashboard("close safety popup");
  return upload_script(follow_script(stale_limit_, acc_, tstep_, dec_default_)) ? Result::Ok : Result::CommError;
}

}  // namespace hrc
