// SPDX-License-Identifier: MIT
#include "hrc/integration.hpp"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <vector>

#include "hrc/common.hpp"
#include "hrc/interfaces.hpp"

#ifdef HRC_HAVE_OPEN62541
#include <open62541/server.h>
#include <open62541/server_config_default.h>
#endif

namespace hrc {

namespace {
void pin(int cpu) {
  if (cpu < 0) return;
  cpu_set_t s;
  CPU_ZERO(&s);
  CPU_SET(cpu, &s);
  pthread_setaffinity_np(pthread_self(), sizeof s, &s);
}
int listen_tcp(int port) {
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  int one = 1;
  setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(static_cast<uint16_t>(port));
  a.sin_addr.s_addr = INADDR_ANY;
  if (::bind(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0 || ::listen(fd, 16) != 0) { ::close(fd); return -1; }
  return fd;
}
uint16_t be16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
void wbe16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v >> 8); p[1] = uint8_t(v); }
int16_t clamp16(double v) { return static_cast<int16_t>(std::clamp(std::lround(v), -32768L, 32767L)); }

// Generic accept/serve loop for request/response TCP protocols with framing callback.
template <class Frame, class Handle>
void serve_loop(int lfd, std::atomic<bool>& run, Frame frame, Handle handle) {
  std::vector<pollfd> fds{{lfd, POLLIN, 0}};
  std::vector<std::string> bufs{""};
  while (run) {
    if (::poll(fds.data(), fds.size(), 100) <= 0) continue;
    for (size_t i = 0; i < fds.size(); ++i) {
      if (!(fds[i].revents & (POLLIN | POLLHUP | POLLERR))) continue;
      if (i == 0) {
        int c = ::accept(lfd, nullptr, nullptr);
        if (c >= 0) {
          int one = 1;
          setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
          fds.push_back({c, POLLIN, 0});
          bufs.emplace_back();
        }
        continue;
      }
      char tmp[4096];
      ssize_t k = ::recv(fds[i].fd, tmp, sizeof tmp, 0);
      if (k <= 0) {
        ::close(fds[i].fd);
        fds.erase(fds.begin() + static_cast<long>(i));
        bufs.erase(bufs.begin() + static_cast<long>(i));
        --i;
        continue;
      }
      const int64_t t_rx = mono_ns();
      bufs[i].append(tmp, static_cast<size_t>(k));
      size_t used;
      while ((used = frame(bufs[i])) > 0) {
        std::string req = bufs[i].substr(0, used);
        bufs[i].erase(0, used);
        std::string rep = handle(req);
        (void)::send(fds[i].fd, rep.data(), rep.size(), MSG_NOSIGNAL);
        (void)t_rx;
      }
    }
  }
  for (size_t i = 1; i < fds.size(); ++i) ::close(fds[i].fd);
}
}  // namespace

// ============================================================================ Modbus TCP
ModbusServer::ModbusServer(IntegrationBus& bus, int port, EventChannel* ev, int cpu) : bus_(bus), port_(port), cpu_(cpu), ev_(ev) {}
ModbusServer::~ModbusServer() { stop(); }
bool ModbusServer::start() {
  lfd_ = listen_tcp(port_);
  if (lfd_ < 0) return false;
  run_ = true;
  th_ = std::thread([this] { loop(); });
  return true;
}
void ModbusServer::stop() {
  if (run_.exchange(false) && th_.joinable()) th_.join();
  if (lfd_ >= 0) ::close(lfd_);
  lfd_ = -1;
}

size_t ModbusServer::handle(const uint8_t* q, size_t n, uint8_t* r) {
  using namespace modbus_map;
  // q points at MBAP header (7 bytes) + PDU
  std::memcpy(r, q, 7);
  const uint8_t fc = q[7];
  const uint8_t* d = q + 8;
  Telemetry t;
  bus_.telemetry.load(t);
  auto holding = [&](int a) -> int16_t {
    if (a >= kHrJointPos && a < kHrJointPos + t.q.n) return clamp16(t.q[a - kHrJointPos] * 1800.0 / M_PI);
    if (a >= kHrJointVel && a < kHrJointVel + t.qd.n) return clamp16(t.qd[a - kHrJointVel] * 100.0);
    if (a == kHrMinDist) return clamp16(std::max(0.0, t.min_sep_m) * 1000.0);
    if (a == kHrOverride || a == kHrOverrideCmd) return clamp16(bus_.override_.load() * 100.0);
    return 0;
  };
  auto input = [&](int a) -> int16_t {
    if (a == kIrPose) return clamp16(t.tcp.x * 1000);
    if (a == kIrPose + 1) return clamp16(t.tcp.y * 1000);
    if (a == kIrPose + 2) return clamp16(t.tcp.z * 1000);
    if (a == kIrPose + 3) return 10000;
    return 0;
  };
  auto coil = [&](int a) -> bool {
    switch (a) {
      case 0: return t.mode < 5;
      case 1: return t.mode == 5 || t.mode == 6;
      case 2: return t.h_geo < 0;
      case 3: return t.mode == 7;
      case 4: return t.mode >= 1 && t.mode <= 4;
      case 5: return t.learned_active;
      case 6: return t.estimate_available;
      case 7: return t.mode == 6 || t.mode == 7;
      default: return false;
    }
  };
  auto exc = [&](uint8_t code) { r[7] = fc | 0x80; r[8] = code; wbe16(r + 4, 3); return size_t(9); };
  size_t len = 0;
  switch (fc) {
    case 0x01: case 0x03: case 0x04: {
      if (n < 12) return exc(0x03);
      int addr = be16(d), cnt = be16(d + 2);
      if (fc == 0x01) {
        if (cnt < 1 || cnt > 2000 || addr + cnt > kNumCoils) return exc(0x02);
        int bytes = (cnt + 7) / 8;
        r[7] = fc; r[8] = static_cast<uint8_t>(bytes);
        std::memset(r + 9, 0, static_cast<size_t>(bytes));
        for (int i = 0; i < cnt; ++i) if (coil(addr + i)) r[9 + i / 8] |= uint8_t(1u << (i % 8));
        len = 9 + static_cast<size_t>(bytes);
      } else {
        int lim = fc == 0x03 ? kNumRegs : kIrPose + 7;
        if (cnt < 1 || cnt > 125 || addr + cnt > lim || (fc == 0x04 && addr < kIrPose)) return exc(0x02);
        r[7] = fc; r[8] = static_cast<uint8_t>(2 * cnt);
        for (int i = 0; i < cnt; ++i) wbe16(r + 9 + 2 * i, static_cast<uint16_t>(fc == 0x03 ? holding(addr + i) : input(addr + i)));
        len = 9 + 2 * static_cast<size_t>(cnt);
      }
      break;
    }
    case 0x05: {  // write single coil
      int addr = be16(d), val = be16(d + 2);
      if (val != 0xFF00 && val != 0x0000) return exc(0x03);
      if (addr < kCoilCmd || addr > kCoilCmd + 2) return exc(0x02);
      if (val == 0xFF00) bus_.mission = addr - kCoilCmd + 1;
      std::memcpy(r + 7, q + 7, 5);
      len = 12;
      break;
    }
    case 0x06: {  // write single register
      int addr = be16(d), val = be16(d + 2);
      if (addr != kHrOverrideCmd) return exc(0x02);
      if (val > 100) return exc(0x03);
      bus_.override_ = val / 100.0;
      std::memcpy(r + 7, q + 7, 5);
      len = 12;
      break;
    }
    case 0x0F: case 0x10: {  // write multiple coils / registers
      int addr = be16(d), cnt = be16(d + 2);
      if (fc == 0x10) {
        if (addr != kHrOverrideCmd || cnt != 1) return exc(0x02);
        int val = be16(d + 5);
        if (val > 100) return exc(0x03);
        bus_.override_ = val / 100.0;
      } else {
        if (addr < kCoilCmd || addr + cnt > kCoilCmd + 3) return exc(0x02);
        for (int i = 0; i < cnt; ++i) if (d[5 + i / 8] & (1u << (i % 8))) bus_.mission = addr + i - kCoilCmd + 1;
      }
      r[7] = fc; wbe16(r + 8, static_cast<uint16_t>(addr)); wbe16(r + 10, static_cast<uint16_t>(cnt));
      len = 12;
      break;
    }
    default:
      return exc(0x01);
  }
  wbe16(r + 4, static_cast<uint16_t>(len - 6));
  return len;
}

void ModbusServer::loop() {
  pin(cpu_);
  serve_loop(lfd_, run_,
             [](const std::string& b) -> size_t {
               if (b.size() < 7) return 0;
               size_t L = 6 + be16(reinterpret_cast<const uint8_t*>(b.data()) + 4);
               return b.size() >= L ? L : 0;
             },
             [this](const std::string& req) {
               const int64_t t0 = mono_ns();
               uint8_t rep[300];
               size_t n = handle(reinterpret_cast<const uint8_t*>(req.data()), req.size(), rep);
               bus_.requests++;
               if (ev_) ev_->emit(EventKind::ProtocolSample, 0, (mono_ns() - t0) * 1e-6, static_cast<uint8_t>(req[7]), "modbus");
               return std::string(reinterpret_cast<char*>(rep), n);
             });
}

// ============================================================================ REST
RestServer::RestServer(IntegrationBus& bus, int port, EventChannel* ev, int cpu) : bus_(bus), port_(port), cpu_(cpu), ev_(ev) {}
RestServer::~RestServer() { stop(); }
bool RestServer::start() {
  lfd_ = listen_tcp(port_);
  if (lfd_ < 0) return false;
  run_ = true;
  th_ = std::thread([this] { loop(); });
  return true;
}
void RestServer::stop() {
  if (run_.exchange(false) && th_.joinable()) th_.join();
  if (lfd_ >= 0) ::close(lfd_);
  lfd_ = -1;
}

std::string RestServer::handle(const std::string& m, const std::string& path, const std::string& body, int& code) {
  code = 200;
  if (m == "GET" && path == "/api/v1/status") {
    Telemetry t;
    bus_.telemetry.load(t);
    JsonWriter w;
    w.begin_object().kv("cycle", static_cast<int64_t>(t.cycle)).kv("mode", static_cast<int64_t>(t.mode))
        .kv("min_separation_m", t.min_sep_m).kv("h_geo", t.h_geo).kv("override", bus_.override_.load())
        .kv("learned_active", t.learned_active).kv("estimate_available", t.estimate_available)
        .kv("task_cycles", static_cast<int64_t>(t.task_cycles));
    w.begin_array("q");
    for (int i = 0; i < t.q.n; ++i) w.value(t.q[i]);
    w.end_array().end_object();
    return w.str();
  }
  if (m == "PUT" && path == "/api/v1/override") {
    try {
      double v = Json::parse(body)["value"].num(-1);
      if (v < 0 || v > 1) { code = 422; return "{\"error\":\"value must be in [0,1]\"}"; }
      bus_.override_ = v;
      return "{\"ok\":true}";
    } catch (...) { code = 400; return "{\"error\":\"bad json\"}"; }
  }
  if (m == "POST" && path.rfind("/api/v1/mission/", 0) == 0) {
    std::string a = path.substr(16);
    if (a == "start") bus_.mission = 1; else if (a == "pause") bus_.mission = 2; else if (a == "abort") bus_.mission = 3;
    else { code = 404; return "{\"error\":\"unknown action\"}"; }
    return "{\"ok\":true}";
  }
  code = 404;
  return "{\"error\":\"not found\"}";
}

void RestServer::loop() {
  pin(cpu_);
  serve_loop(lfd_, run_,
             [](const std::string& b) -> size_t {
               size_t he = b.find("\r\n\r\n");
               if (he == std::string::npos) return 0;
               size_t cl = 0, p = b.find("Content-Length:");
               if (p == std::string::npos) p = b.find("content-length:");
               if (p != std::string::npos && p < he) cl = std::stoul(b.substr(p + 15));
               return b.size() >= he + 4 + cl ? he + 4 + cl : 0;
             },
             [this](const std::string& req) {
               const int64_t t0 = mono_ns();
               size_t sp1 = req.find(' '), sp2 = req.find(' ', sp1 + 1);
               std::string m = req.substr(0, sp1), path = req.substr(sp1 + 1, sp2 - sp1 - 1);
               std::string body = req.substr(req.find("\r\n\r\n") + 4);
               int code;
               std::string out = handle(m, path, body, code);
               std::string rep = "HTTP/1.1 " + std::to_string(code) + (code == 200 ? " OK" : " ERR") +
                                 "\r\nContent-Type: application/json\r\nContent-Length: " + std::to_string(out.size()) +
                                 "\r\nConnection: keep-alive\r\n\r\n" + out;
               bus_.requests++;
               if (ev_) ev_->emit(EventKind::ProtocolSample, 0, (mono_ns() - t0) * 1e-6, code, "rest");
               return rep;
             });
}

// ============================================================================ OPC-UA
OpcUaServer::OpcUaServer(IntegrationBus& bus, int port, EventChannel* ev, int cpu) : bus_(bus), port_(port), cpu_(cpu), ev_(ev) {}
OpcUaServer::~OpcUaServer() { stop(); }
#ifdef HRC_HAVE_OPEN62541
bool OpcUaServer::available() const { return true; }
#else
bool OpcUaServer::available() const { return false; }
#endif
bool OpcUaServer::start() {
  if (!available()) return false;
  run_ = true;
  th_ = std::thread([this] { loop(); });
  return true;
}
void OpcUaServer::stop() {
  if (run_.exchange(false) && th_.joinable()) th_.join();
}

#ifdef HRC_HAVE_OPEN62541
namespace {
UA_NodeId add_var(UA_Server* s, UA_NodeId parent, const char* name, const UA_DataType* type, int dims) {
  UA_VariableAttributes a = UA_VariableAttributes_default;
  a.displayName = UA_LOCALIZEDTEXT(const_cast<char*>("en-US"), const_cast<char*>(name));
  a.dataType = type->typeId;
  a.accessLevel = UA_ACCESSLEVELMASK_READ;
  if (dims > 0) { a.valueRank = UA_VALUERANK_ONE_DIMENSION; }
  UA_NodeId id = UA_NODEID_STRING(1, const_cast<char*>(name));
  UA_Server_addVariableNode(s, id, parent, UA_NODEID_NUMERIC(0, UA_NS0ID_HASCOMPONENT),
                            UA_QUALIFIEDNAME(1, const_cast<char*>(name)), UA_NODEID_NUMERIC(0, UA_NS0ID_BASEDATAVARIABLETYPE),
                            a, nullptr, nullptr);
  return id;
}
}  // namespace

void OpcUaServer::loop() {
  pin(cpu_);
  UA_Server* s = UA_Server_new();
  UA_ServerConfig_setMinimal(UA_Server_getConfig(s), static_cast<UA_UInt16>(port_), nullptr);
  UA_ObjectAttributes oa = UA_ObjectAttributes_default;
  oa.displayName = UA_LOCALIZEDTEXT(const_cast<char*>("en-US"), const_cast<char*>("HRC_System"));
  UA_NodeId sys = UA_NODEID_STRING(1, const_cast<char*>("HRC_System"));
  UA_Server_addObjectNode(s, sys, UA_NODEID_NUMERIC(0, UA_NS0ID_OBJECTSFOLDER), UA_NODEID_NUMERIC(0, UA_NS0ID_ORGANIZES),
                          UA_QUALIFIEDNAME(1, const_cast<char*>("HRC_System")), UA_NODEID_NUMERIC(0, UA_NS0ID_BASEOBJECTTYPE),
                          oa, nullptr, nullptr);
  UA_NodeId jp = add_var(s, sys, "Robot.JointPositions", &UA_TYPES[UA_TYPES_DOUBLE], 1);
  UA_NodeId md = add_var(s, sys, "Safety.MinimumDistance", &UA_TYPES[UA_TYPES_DOUBLE], 0);
  UA_NodeId cv = add_var(s, sys, "Safety.ConstraintValue", &UA_TYPES[UA_TYPES_DOUBLE], 0);
  UA_NodeId st = add_var(s, sys, "Robot.OperationalState", &UA_TYPES[UA_TYPES_BYTE], 0);
  UA_Server_run_startup(s);
  int64_t next = mono_ns();
  while (run_) {
    UA_Server_run_iterate(s, false);
    if (mono_ns() >= next) {
      next += 50'000'000;  // 50 ms sampling, as the information model specifies
      Telemetry t;
      bus_.telemetry.load(t);
      UA_Variant v;
      UA_Variant_setArray(&v, t.q.v.data(), static_cast<size_t>(t.q.n), &UA_TYPES[UA_TYPES_DOUBLE]);
      UA_Server_writeValue(s, jp, v);
      UA_Variant_setScalar(&v, &t.min_sep_m, &UA_TYPES[UA_TYPES_DOUBLE]);
      UA_Server_writeValue(s, md, v);
      UA_Variant_setScalar(&v, &t.h_geo, &UA_TYPES[UA_TYPES_DOUBLE]);
      UA_Server_writeValue(s, cv, v);
      UA_Byte m = t.mode;
      UA_Variant_setScalar(&v, &m, &UA_TYPES[UA_TYPES_BYTE]);
      UA_Server_writeValue(s, st, v);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  UA_Server_run_shutdown(s);
  UA_Server_delete(s);
}
#else
void OpcUaServer::loop() {}
#endif

}  // namespace hrc
