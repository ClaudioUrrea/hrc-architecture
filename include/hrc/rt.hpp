// SPDX-License-Identifier: MIT
#pragma once
#include <string>

namespace hrc {

struct RtSettings {
  std::string policy = "fifo";  // fifo | other
  int priority = 90;
  int cpu = -1;                 // -1: no affinity
  bool lock_memory = true;
};

struct RtApplied {
  bool policy_ok = false, affinity_ok = false, mlock_ok = false;
  std::string error;
  std::string to_json() const;
};

// Applies the settings to the calling thread. Never throws: failures are reported in the
// result and written to the run manifest, so a run without real-time scheduling cannot be
// mistaken for one with it.
RtApplied apply_rt(const RtSettings& s);

}  // namespace hrc
