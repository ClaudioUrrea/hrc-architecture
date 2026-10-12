// SPDX-License-Identifier: MIT
#include "hrc/rt.hpp"

#include <pthread.h>
#include <sched.h>
#include <sys/mman.h>

#include <cerrno>
#include <cstring>

#include "hrc/common.hpp"

namespace hrc {

std::string RtApplied::to_json() const {
  JsonWriter w;
  w.begin_object().kv("policy_ok", policy_ok).kv("affinity_ok", affinity_ok).kv("mlock_ok", mlock_ok).kv("error", error).end_object();
  return w.str();
}

RtApplied apply_rt(const RtSettings& s) {
  RtApplied r;
  if (s.lock_memory) {
    r.mlock_ok = mlockall(MCL_CURRENT | MCL_FUTURE) == 0;
    if (!r.mlock_ok) r.error += std::string("mlockall: ") + std::strerror(errno) + "; ";
  } else {
    r.mlock_ok = true;
  }
  sched_param sp{};
  int pol = SCHED_OTHER;
  if (s.policy == "fifo") { pol = SCHED_FIFO; sp.sched_priority = s.priority; }
  int e = pthread_setschedparam(pthread_self(), pol, &sp);
  r.policy_ok = e == 0;
  if (e) r.error += std::string("setschedparam: ") + std::strerror(e) + "; ";
  if (s.cpu >= 0) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(s.cpu, &set);
    e = pthread_setaffinity_np(pthread_self(), sizeof set, &set);
    r.affinity_ok = e == 0;
    if (e) r.error += std::string("setaffinity: ") + std::strerror(e) + "; ";
  } else {
    r.affinity_ok = true;
  }
  return r;
}

}  // namespace hrc
