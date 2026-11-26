// SPDX-License-Identifier: MIT
// Client-side load generator for the integration layer. Issues Modbus TCP and REST requests
// against a running hrc_run instance at a configured rate and writes one CSV row per request
// (client send -> reply received), inside its own run directory with SHA-256 manifest.
//
//   hrc_protocol_bench --host 127.0.0.1 --modbus-port 5020 --rest-port 8080
//                      --rate-per-min 50 --duration 600 [--peak-per-min 112] [--backup DIR]
#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <random>
#include <string>
#include <thread>
#include <vector>

#include "hrc/common.hpp"

using namespace hrc;
namespace fs = std::filesystem;

namespace {
int conn(const std::string& host, int port) {
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(static_cast<uint16_t>(port));
  inet_pton(AF_INET, host.c_str(), &a.sin_addr);
  if (::connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) { ::close(fd); return -1; }
  int one = 1;
  setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
  return fd;
}
bool recv_some(int fd, std::string& out, size_t need, int ms) {
  char b[4096];
  while (out.size() < need) {
    pollfd p{fd, POLLIN, 0};
    if (::poll(&p, 1, ms) <= 0) return false;
    ssize_t k = ::recv(fd, b, sizeof b, 0);
    if (k <= 0) return false;
    out.append(b, static_cast<size_t>(k));
  }
  return true;
}
}  // namespace

int main(int argc, char** argv) {
  std::string host = "127.0.0.1", root = "runs";
  std::vector<std::string> backups;
  int mport = 5020, rport = 8080;
  double rate = 50, peak = 112, dur = 60;
  uint64_t seed = 7;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string a = argv[i], v = argv[i + 1];
    if (a == "--host") host = v;
    else if (a == "--modbus-port") mport = std::stoi(v);
    else if (a == "--rest-port") rport = std::stoi(v);
    else if (a == "--rate-per-min") rate = std::stod(v);
    else if (a == "--peak-per-min") peak = std::stod(v);
    else if (a == "--duration") dur = std::stod(v);
    else if (a == "--seed") seed = std::stoull(v);
    else if (a == "--run-root") root = v;
    else if (a == "--backup") backups.push_back(v);
  }
  std::string ts = utc_iso8601(wall_ns());
  for (auto& ch : ts) if (ch == ':') ch = '-';
  fs::path dir = fs::path(root) / (ts + "_protocol_bench");
  fs::create_directories(dir);
  std::ofstream csv(dir / "protocol_client.csv");
  csv << "t_send_ns,protocol,op,ok,rtt_us\n";
  int mfd = conn(host, mport), rfd = conn(host, rport);
  std::mt19937_64 rng(seed);
  std::uniform_real_distribution<double> U(0, 1);
  const int64_t t_end = mono_ns() + static_cast<int64_t>(dur * 1e9);
  uint16_t tid = 0;
  uint64_t n = 0;
  while (mono_ns() < t_end) {
    // Poisson arrivals; every 5th minute runs at the peak rate
    double minute = (dur - (t_end - mono_ns()) * 1e-9) / 60.0;
    double r = (static_cast<int>(minute) % 5 == 4) ? peak : rate;
    std::exponential_distribution<double> gap(r / 60.0);
    std::this_thread::sleep_for(std::chrono::duration<double>(gap(rng)));
    const double u = U(rng);
    std::string proto, op;
    bool ok = false;
    int64_t t0 = mono_ns(), t1 = t0;
    if (u < 0.5 && mfd >= 0) {
      // FC03 read 10 holding registers, FC01 read 8 coils, FC06 write override
      uint8_t q[12] = {0, 0, 0, 0, 0, 6, 1, 3, 0, 0, 0, 10};
      double v = U(rng);
      if (v < 0.25) { q[7] = 1; q[11] = 8; op = "fc01"; }
      else if (v < 0.35) { q[7] = 6; q[9] = 30; q[10] = 0; q[11] = 100; op = "fc06"; }
      else op = "fc03";
      ++tid; q[0] = uint8_t(tid >> 8); q[1] = uint8_t(tid);
      proto = "modbus";
      t0 = mono_ns();
      ::send(mfd, q, sizeof q, MSG_NOSIGNAL);
      std::string rep;
      ok = recv_some(mfd, rep, 7, 1000) && recv_some(mfd, rep, 6 + ((uint8_t(rep[4]) << 8) | uint8_t(rep[5])), 1000) && !(uint8_t(rep[7]) & 0x80);
      t1 = mono_ns();
    } else if (rfd >= 0) {
      proto = "rest";
      op = "get_status";
      std::string req = "GET /api/v1/status HTTP/1.1\r\nHost: x\r\n\r\n";
      t0 = mono_ns();
      ::send(rfd, req.data(), req.size(), MSG_NOSIGNAL);
      std::string rep;
      ok = recv_some(rfd, rep, 1, 1000);
      while (ok) {
        size_t he = rep.find("\r\n\r\n");
        if (he != std::string::npos) {
          size_t p = rep.find("Content-Length: ");
          size_t cl = p != std::string::npos ? std::stoul(rep.substr(p + 16)) : 0;
          if (rep.size() >= he + 4 + cl) break;
        }
        ok = recv_some(rfd, rep, rep.size() + 1, 1000);
      }
      ok = ok && rep.rfind("HTTP/1.1 200", 0) == 0;
      t1 = mono_ns();
    } else {
      continue;
    }
    csv << t0 << "," << proto << "," << op << "," << (ok ? 1 : 0) << "," << (t1 - t0) / 1000.0 << "\n";
    ++n;
  }
  csv.close();
  JsonWriter w;
  w.begin_object().kv("experiment", "protocol_bench").kv("requests", static_cast<int64_t>(n)).kv("rate_per_min", rate)
      .kv("peak_per_min", peak).kv("duration_s", dur).kv("seed", static_cast<int64_t>(seed)).kv("host", host)
      .kv("data_kind", "raw client-side measurements written by the benchmark; never edited")
      .kv("end_utc", utc_iso8601(wall_ns())).end_object();
  write_text_file((dir / "manifest.json").string(), w.str());
  std::string man;
  for (const char* f : {"manifest.json", "protocol_client.csv"}) man += sha256_file((dir / f).string()) + "  " + f + "\n";
  write_text_file((dir / "MANIFEST.sha256").string(), man);
  for (auto& b : backups) {
    fs::path dst = fs::path(b) / dir.filename();
    fs::create_directories(dst);
    for (auto& e : fs::directory_iterator(dir)) fs::copy_file(e.path(), dst / e.path().filename(), fs::copy_options::overwrite_existing);
  }
  std::fprintf(stderr, "[bench] %llu requests -> %s\n", static_cast<unsigned long long>(n), dir.c_str());
  return 0;
}
