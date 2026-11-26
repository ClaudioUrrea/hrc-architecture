// SPDX-License-Identifier: MIT
// Raw-data logger and provenance chain.
//
// Every experiment writes one run directory:
//   runs/<run_id>/config.json        exact configuration used (byte copy)
//   runs/<run_id>/manifest.json      host, kernel, build, git commit, start/end, counts, status
//   runs/<run_id>/schema.json        byte layout of cycles.bin
//   runs/<run_id>/cycles.bin         one 128-byte CycleRecord per control cycle (raw, never edited)
//   runs/<run_id>/events.jsonl       fault injections, detections, mode changes, ...
//   runs/<run_id>/MANIFEST.sha256    SHA-256 of every file above, written last
// After close() the directory is copied to every backup target and the copy is verified
// hash by hash. A run whose process died keeps status "incomplete" and is reported as such
// by the analysis, never silently dropped.
#pragma once
#include <atomic>
#include <cstdio>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "hrc/common.hpp"
#include "hrc/records.hpp"
#include "hrc/spsc.hpp"

namespace hrc {

struct RunInfo {
  std::string run_root = "runs";
  std::string experiment;          // e.g. "timing_campaign", "ablation", "fault_campaign"
  std::string variant;             // e.g. "A3", "block_017"
  std::string config_path;         // copied verbatim into the run directory
  std::vector<std::string> backup_dirs;
  std::string notes;
};

class EventChannel {
 public:
  explicit EventChannel(std::string name) : name_(std::move(name)), ring_(4096) {}
  void emit(EventKind k, uint8_t category, double value = 0, int32_t detail = 0, const char* text = nullptr,
            uint8_t a = 0, uint8_t b = 0);
  const std::string& name() const { return name_; }
  SpscRing<EventRecord>& ring() { return ring_; }

 private:
  std::string name_;
  SpscRing<EventRecord> ring_;
};

class RunLogger {
 public:
  RunLogger() = default;
  ~RunLogger();
  RunLogger(const RunLogger&) = delete;
  RunLogger& operator=(const RunLogger&) = delete;

  // Creates the run directory and starts the writer thread. Returns the run directory.
  std::string open(const RunInfo& info);
  // Real-time safe. Returns false (and counts a drop) if the ring is full.
  bool push_cycle(const CycleRecord& r) { return cycles_ ? cycles_->push(r) : false; }
  // Each producing thread obtains its own channel once, before the real-time phase.
  EventChannel* channel(const std::string& name);
  // Adds a key/value to the final manifest (non-RT).
  void annotate(const std::string& key, const std::string& raw_json);
  // Stops the writer, finalizes manifest and hashes, mirrors to backups and verifies them.
  // Returns true only if every backup copy verified.
  bool close(const std::string& status = "complete");
  const std::string& dir() const { return dir_; }
  uint64_t cycles_written() const { return n_cycles_; }

 private:
  void writer_loop();
  void drain();
  void write_manifest(const std::string& status, bool final_);
  bool mirror_and_verify(const std::string& target_root, std::string& report);

  RunInfo info_;
  std::string run_id_, dir_;
  int64_t t_start_wall_ = 0, t_start_mono_ = 0;
  std::unique_ptr<SpscRing<CycleRecord>> cycles_;
  std::vector<std::unique_ptr<EventChannel>> channels_;
  std::mutex chan_mu_;
  std::vector<std::pair<std::string, std::string>> annotations_;
  std::FILE* f_cycles_ = nullptr;
  std::FILE* f_events_ = nullptr;
  std::thread writer_;
  std::atomic<bool> stop_{false};
  uint64_t n_cycles_ = 0, n_events_ = 0;
  bool open_ = false;
  std::string host_json_;
};

std::string host_description_json();  // uname, CPU, kernel cmdline, RT settings, compiler, git

}  // namespace hrc
