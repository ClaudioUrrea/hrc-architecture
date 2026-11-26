// SPDX-License-Identifier: MIT
#include "hrc/run_logger.hpp"

#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>

#include "hrc/interfaces.hpp"

#ifndef HRC_GIT_COMMIT
#define HRC_GIT_COMMIT "unknown"
#endif
#ifndef HRC_BUILD_TYPE
#define HRC_BUILD_TYPE "unknown"
#endif

namespace fs = std::filesystem;

namespace hrc {

void EventChannel::emit(EventKind k, uint8_t category, double value, int32_t detail, const char* text, uint8_t a,
                        uint8_t b) {
  EventRecord e{};
  e.t_ns = mono_ns();
  e.kind = k;
  e.category = category;
  e.value = value;
  e.detail = detail;
  e.a = a;
  e.b = b;
  if (text) std::strncpy(e.text, text, sizeof(e.text) - 1);
  ring_.push(e);
}

std::string host_description_json() {
  utsname u{};
  uname(&u);
  JsonWriter w;
  w.begin_object();
  w.kv("hostname", std::string(u.nodename));
  w.kv("kernel_release", std::string(u.release));
  w.kv("kernel_version", std::string(u.version));
  w.kv("machine", std::string(u.machine));
  w.kv("cpu_model", shell_capture("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //'"));
  w.kv("cpu_count_online", static_cast<int64_t>(sysconf(_SC_NPROCESSORS_ONLN)));
  w.kv("kernel_cmdline", shell_capture("cat /proc/cmdline"));
  w.kv("preempt_rt", shell_capture("cat /sys/kernel/realtime") == "1" ||
                         std::string(u.version).find("PREEMPT_RT") != std::string::npos ||
                         std::string(u.version).find("PREEMPT RT") != std::string::npos);
  w.kv("sched_rt_runtime_us", shell_capture("cat /proc/sys/kernel/sched_rt_runtime_us"));
  w.kv("isolated_cpus", shell_capture("cat /sys/devices/system/cpu/isolated"));
  w.kv("cpufreq_governor", shell_capture("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"));
  w.kv("mem_total", shell_capture("grep MemTotal /proc/meminfo | awk '{print $2\" \"$3}'"));
  w.kv("os_release", shell_capture(". /etc/os-release && echo \"$PRETTY_NAME\""));
  w.kv("compiler", std::string(__VERSION__));
  w.kv("build_type", std::string(HRC_BUILD_TYPE));
  w.kv("git_commit", std::string(HRC_GIT_COMMIT));
  w.kv("git_dirty_at_runtime", shell_capture("git status --porcelain 2>/dev/null | head -c 1"));
  w.kv("user", shell_capture("id -un"));
  w.end_object();
  return w.str();
}

static std::string schema_json() {
  // Offsets mirror CycleRecord; analysis/hrc_logs.py checks them against this file.
  struct F { const char* n; const char* t; size_t off; };
  const F fields[] = {
      {"idx", "u8", offsetof(CycleRecord, idx)},
      {"t_release_ns", "i8", offsetof(CycleRecord, t_release_ns)},
      {"t_wake_ns", "i8", offsetof(CycleRecord, t_wake_ns)},
      {"t_end_ns", "i8", offsetof(CycleRecord, t_end_ns)},
      {"d_state_ns", "i4", offsetof(CycleRecord, d_state_ns)},
      {"d_nominal_ns", "i4", offsetof(CycleRecord, d_nominal_ns)},
      {"d_geo_ns", "i4", offsetof(CycleRecord, d_geo_ns)},
      {"d_learned_ns", "i4", offsetof(CycleRecord, d_learned_ns)},
      {"d_remote_compute_ns", "i4", offsetof(CycleRecord, d_remote_compute_ns)},
      {"d_qp_ns", "i4", offsetof(CycleRecord, d_qp_ns)},
      {"d_dispatch_ns", "i4", offsetof(CycleRecord, d_dispatch_ns)},
      {"d_log_ns", "i4", offsetof(CycleRecord, d_log_ns)},
      {"h_geo", "f4", offsetof(CycleRecord, h_geo)},
      {"h_learned", "f4", offsetof(CycleRecord, h_learned)},
      {"min_sep_m", "f4", offsetof(CycleRecord, min_sep_m)},
      {"human_age_ms", "f4", offsetof(CycleRecord, human_age_ms)},
      {"psd_m", "f4", offsetof(CycleRecord, psd_m)},
      {"speed_scale", "f4", offsetof(CycleRecord, speed_scale)},
      {"qd_norm", "f4", offsetof(CycleRecord, qd_norm)},
      {"mean_conf", "f4", offsetof(CycleRecord, mean_conf)},
      {"flags", "u2", offsetof(CycleRecord, flags)},
      {"mode", "u1", offsetof(CycleRecord, mode)},
      {"qp_iters", "u1", offsetof(CycleRecord, qp_iters)},
      {"qp_rows", "u1", offsetof(CycleRecord, qp_rows)},
      {"streams_alive", "u1", offsetof(CycleRecord, streams_alive)},
  };
  struct A { const char* n; size_t off; int count; };
  const A arrays[] = {{"q", offsetof(CycleRecord, q), 7}, {"qd_cmd", offsetof(CycleRecord, qd_cmd), 7},
                      {"closest_kp", offsetof(CycleRecord, closest_kp), 3}};
  JsonWriter w;
  w.begin_object();
  w.kv("record", "CycleRecord");
  w.kv("byte_order", "little");
  w.kv("size", static_cast<int64_t>(sizeof(CycleRecord)));
  w.begin_array("fields");
  for (auto& f : fields) {
    w.begin_object().kv("name", f.n).kv("type", f.t).kv("offset", static_cast<int64_t>(f.off)).end_object();
  }
  for (auto& a : arrays) {
    w.begin_object().kv("name", a.n).kv("type", "f4").kv("offset", static_cast<int64_t>(a.off)).kv("count", a.count).end_object();
  }
  w.end_array();
  w.end_object();
  return w.str();
}

RunLogger::~RunLogger() {
  if (open_) close("incomplete");
}

std::string RunLogger::open(const RunInfo& info) {
  info_ = info;
  t_start_wall_ = wall_ns();
  t_start_mono_ = mono_ns();
  std::string ts = utc_iso8601(t_start_wall_);
  std::replace(ts.begin(), ts.end(), ':', '-');
  run_id_ = ts + "_" + info.experiment + (info.variant.empty() ? "" : "_" + info.variant);
  dir_ = (fs::path(info.run_root) / run_id_).string();
  fs::create_directories(dir_);
  if (!info.config_path.empty()) fs::copy_file(info.config_path, fs::path(dir_) / "config.json",
                                                fs::copy_options::overwrite_existing);
  write_text_file((fs::path(dir_) / "schema.json").string(), schema_json());
  host_json_ = host_description_json();
  f_cycles_ = std::fopen((fs::path(dir_) / "cycles.bin").c_str(), "wb");
  f_events_ = std::fopen((fs::path(dir_) / "events.jsonl").c_str(), "wb");
  if (!f_cycles_ || !f_events_) throw std::runtime_error("RunLogger: cannot open output files in " + dir_);
  cycles_ = std::make_unique<SpscRing<CycleRecord>>(1u << 16);
  write_manifest("running", false);
  open_ = true;
  stop_ = false;
  writer_ = std::thread([this] { writer_loop(); });
  return dir_;
}

EventChannel* RunLogger::channel(const std::string& name) {
  std::lock_guard<std::mutex> lk(chan_mu_);
  channels_.push_back(std::make_unique<EventChannel>(name));
  return channels_.back().get();
}

void RunLogger::annotate(const std::string& key, const std::string& raw_json) {
  std::lock_guard<std::mutex> lk(chan_mu_);
  annotations_.emplace_back(key, raw_json);
}

static const char* kind_name(EventKind k) {
  switch (k) {
    case EventKind::Info: return "info";
    case EventKind::FaultInjected: return "fault_injected";
    case EventKind::FaultDetected: return "fault_detected";
    case EventKind::FaultCleared: return "fault_cleared";
    case EventKind::ModeChange: return "mode_change";
    case EventKind::RecoveryComplete: return "recovery_complete";
    case EventKind::OperatorAck: return "operator_ack";
    case EventKind::ProtocolSample: return "protocol_sample";
    case EventKind::ConformanceItem: return "conformance_item";
    case EventKind::Warning: return "warning";
  }
  return "?";
}

void RunLogger::drain() {
  CycleRecord r;
  while (cycles_->pop(r)) {
    if (std::fwrite(&r, sizeof r, 1, f_cycles_) == 1) ++n_cycles_;
  }
  std::vector<EventChannel*> chans;
  {
    std::lock_guard<std::mutex> lk(chan_mu_);
    for (auto& c : channels_) chans.push_back(c.get());
  }
  EventRecord e;
  char line[512];
  for (auto* c : chans) {
    while (c->ring().pop(e)) {
      std::string text = JsonWriter::escape(std::string(e.text, strnlen(e.text, sizeof e.text)));
      int n = std::snprintf(line, sizeof line,
                            "{\"t_ns\":%lld,\"t_rel_s\":%.9f,\"src\":\"%s\",\"kind\":\"%s\",\"category\":\"%s\","
                            "\"a\":%u,\"b\":%u,\"detail\":%d,\"value\":%.9g,\"text\":\"%s\"}\n",
                            static_cast<long long>(e.t_ns), (e.t_ns - t_start_mono_) * 1e-9, c->name().c_str(),
                            kind_name(e.kind), to_string(static_cast<FaultCategory>(e.category)), e.a, e.b,
                            e.detail, std::isfinite(e.value) ? e.value : 0.0, text.c_str());
      if (n > 0) { std::fwrite(line, 1, static_cast<size_t>(std::min(n, 511)), f_events_); ++n_events_; }
    }
  }
}

void RunLogger::writer_loop() {
  int64_t last_sync = mono_ns();
  while (!stop_.load()) {
    drain();
    std::fflush(f_cycles_);
    std::fflush(f_events_);
    if (mono_ns() - last_sync > 5'000'000'000LL) {  // fsync every 5 s: a crash loses at most ~5 s
      fsync(fileno(f_cycles_));
      fsync(fileno(f_events_));
      last_sync = mono_ns();
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  drain();
}

void RunLogger::write_manifest(const std::string& status, bool final_) {
  JsonWriter w;
  w.begin_object();
  w.kv("run_id", run_id_);
  w.kv("experiment", info_.experiment);
  w.kv("variant", info_.variant);
  w.kv("status", status);
  w.kv("data_kind", "raw instrument log written by the running software; never edited after close");
  w.kv("start_utc", utc_iso8601(t_start_wall_));
  w.kv("start_mono_ns", t_start_mono_);
  if (final_) {
    w.kv("end_utc", utc_iso8601(wall_ns()));
    w.kv("duration_s", (mono_ns() - t_start_mono_) * 1e-9);
    w.kv("cycles_written", static_cast<int64_t>(n_cycles_));
    w.kv("cycles_dropped_by_logger", static_cast<int64_t>(cycles_ ? cycles_->dropped() : 0));
    w.kv("events_written", static_cast<int64_t>(n_events_));
    int64_t ev_drop = 0;
    for (auto& c : channels_) ev_drop += static_cast<int64_t>(c->ring().dropped());
    w.kv("events_dropped_by_logger", ev_drop);
  }
  w.kv("config_sha256", info_.config_path.empty() ? std::string("") : sha256_file(info_.config_path));
  w.kv("notes", info_.notes);
  w.key_raw("host", host_json_);
  for (auto& a : annotations_) w.key_raw(a.first, a.second);
  w.end_object();
  write_text_file((fs::path(dir_) / "manifest.json").string(), w.str());
}

bool RunLogger::mirror_and_verify(const std::string& target_root, std::string& report) {
  try {
    fs::path dst = fs::path(target_root) / run_id_;
    fs::create_directories(dst);
    for (auto& e : fs::directory_iterator(dir_)) {
      fs::copy_file(e.path(), dst / e.path().filename(), fs::copy_options::overwrite_existing);
    }
    // verify every line of MANIFEST.sha256 at the destination
    std::ifstream m((dst / "MANIFEST.sha256").string());
    std::string line;
    int ok = 0, bad = 0;
    while (std::getline(m, line)) {
      if (line.size() < 67) continue;
      std::string h = line.substr(0, 64), name = line.substr(66);
      if (sha256_file((dst / name).string()) == h) ++ok; else ++bad;
    }
    report += target_root + ": " + std::to_string(ok) + " verified, " + std::to_string(bad) + " mismatched; ";
    return bad == 0 && ok > 0;
  } catch (const std::exception& ex) {
    report += target_root + ": FAILED (" + ex.what() + "); ";
    return false;
  }
}

bool RunLogger::close(const std::string& status) {
  if (!open_) return false;
  stop_ = true;
  if (writer_.joinable()) writer_.join();
  std::fflush(f_cycles_);
  std::fflush(f_events_);
  fsync(fileno(f_cycles_));
  fsync(fileno(f_events_));
  std::fclose(f_cycles_);
  std::fclose(f_events_);
  f_cycles_ = f_events_ = nullptr;
  write_manifest(status, true);

  // MANIFEST.sha256 in `sha256sum` format so it can be checked with standard tools.
  std::vector<std::string> names;
  for (auto& e : fs::directory_iterator(dir_)) {
    std::string n = e.path().filename().string();
    if (n != "MANIFEST.sha256") names.push_back(n);
  }
  std::sort(names.begin(), names.end());
  std::string man;
  for (auto& n : names) man += sha256_file((fs::path(dir_) / n).string()) + "  " + n + "\n";
  write_text_file((fs::path(dir_) / "MANIFEST.sha256").string(), man);
  // make the primary copy read-only
  for (auto& e : fs::directory_iterator(dir_)) chmod(e.path().c_str(), 0444);

  bool all_ok = true;
  std::string report;
  for (auto& b : info_.backup_dirs) all_ok = mirror_and_verify(b, report) && all_ok;

  // append to the run index (one line per run, never rewritten)
  std::string idx = (fs::path(info_.run_root) / "INDEX.csv").string();
  bool new_file = !fs::exists(idx);
  std::ofstream f(idx, std::ios::app);
  if (new_file) f << "run_id,experiment,variant,status,start_utc,cycles,manifest_sha256,backups\n";
  f << run_id_ << "," << info_.experiment << "," << info_.variant << "," << status << ","
    << utc_iso8601(t_start_wall_) << "," << n_cycles_ << ","
    << sha256_file((fs::path(dir_) / "MANIFEST.sha256").string()) << ",\""
    << (info_.backup_dirs.empty() ? std::string("NONE") : report) << "\"\n";
  open_ = false;
  std::fprintf(stderr, "[logger] run %s closed (%s), %llu cycles. Backups: %s\n", run_id_.c_str(), status.c_str(),
               static_cast<unsigned long long>(n_cycles_), info_.backup_dirs.empty() ? "NONE CONFIGURED" : report.c_str());
  return info_.backup_dirs.empty() ? false : all_ok;
}

}  // namespace hrc
