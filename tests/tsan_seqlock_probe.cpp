// SPDX-License-Identifier: MIT
// Positive control for the race detector: the same writer/reader stress as test_r31, compiled
// against whichever include/hrc/spsc.hpp is first on the include path. Built with
// -fsanitize=thread against the 3.0 header (tag campaign-v3-report) it must produce
// ThreadSanitizer data-race reports; against the 3.1 header it must produce none.
//   g++ -std=c++17 -fsanitize=thread -g -O1 -I<tree>/include tests/tsan_seqlock_probe.cpp -o probe
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <thread>

#include "hrc/spsc.hpp"

struct Payload {
  uint64_t k;
  double v[39];
  uint32_t tail;
};

int main() {
  hrc::SeqlockSlot<Payload> slot;
  std::atomic<bool> run{true};
  std::atomic<uint64_t> torn{0}, reads{0};
  std::thread w([&] {
    Payload p{};
    for (uint64_t k = 1; run.load(std::memory_order_relaxed); ++k) {
      p.k = k;
      for (auto& x : p.v) x = static_cast<double>(k);
      p.tail = static_cast<uint32_t>(k);
      slot.store(p);
    }
  });
  std::thread r([&] {
    Payload p{};
    while (run.load(std::memory_order_relaxed)) {
      if (!slot.load(p)) continue;
      reads.fetch_add(1, std::memory_order_relaxed);
      bool ok = p.tail == static_cast<uint32_t>(p.k);
      for (double x : p.v) ok = ok && x == static_cast<double>(p.k);
      if (!ok) torn.fetch_add(1, std::memory_order_relaxed);
    }
  });
  std::this_thread::sleep_for(std::chrono::seconds(2));
  run = false;
  w.join();
  r.join();
  std::printf("reads=%llu torn=%llu\n", static_cast<unsigned long long>(reads.load()), static_cast<unsigned long long>(torn.load()));
  return 0;
}
