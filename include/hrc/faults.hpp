// SPDX-License-Identifier: MIT
// Fault injection campaign. The schedule is generated once from the seed before the run and
// written into the run directory (injection_schedule.csv) *before* the first cycle, so the
// injections are fixed in advance and every injection is also logged at the moment it fires.
//
// Arrival processes:
//   poisson    independent homogeneous Poisson process per category (rate per hour)
//   clustered  Neyman-Scott: cluster centres Poisson at rate/mean_cluster_size, each with a
//              Poisson number of events (mean mean_cluster_size, at least 1), offsets
//              exponential with mean cluster_spread_s; same long-run rate as `poisson`
//   weibull    renewal process with Weibull inter-arrival times of shape k and the same mean
#pragma once
#include <atomic>
#include <cstdint>
#include <functional>
#include <string>
#include <thread>
#include <vector>

#include "hrc/interfaces.hpp"
#include "hrc/run_logger.hpp"

namespace hrc {

struct Injection {
  double t_s = 0;
  FaultCategory category = FaultCategory::None;
  double duration_s = 0;  // sensor timeout / tracking loss / partition
  int param = 0;          // camera index, number of corrupt responses, overrun ms, ...
};

struct FaultCampaignParams {
  bool enabled = false;
  std::string arrival = "poisson";
  double mean_cluster_size = 3.0, cluster_spread_s = 30.0, weibull_shape = 1.0;
  // rates per hour; rate source documented in cfg/fault_rates.md
  double rate_sensor_timeout = 0, rate_tracking_loss = 0, rate_network_partition = 0, rate_overrun = 0,
         rate_hw_comm = 0, rate_memory = 0, rate_config = 0, rate_constraint = 0;
  double rate_scale = 1.0;
  uint64_t seed = 1;
};

std::vector<Injection> make_schedule(const FaultCampaignParams& p, double duration_s);
void write_schedule_csv(const std::vector<Injection>& s, const std::string& path);

// Targets the injector acts on; set by the application.
struct InjectionTargets {
  std::function<void(int cam, double s)> stream_timeout;
  std::function<void(double s)> confidence_drop;
  std::function<void(double s)> partition;
  std::function<void(int n)> comm_faults;
  std::function<void(double s)> lunge;
  std::function<void()> bad_config;
  std::atomic<int> overrun_ms{0};      // consumed by the control thread
  std::atomic<bool> memory_fault{false};
};

class FaultInjector {
 public:
  FaultInjector(std::vector<Injection> schedule, InjectionTargets& targets, EventChannel* ev, int64_t t0_ns);
  ~FaultInjector();
  void start();
  void stop();

 private:
  void loop();
  std::vector<Injection> s_;
  InjectionTargets& tg_;
  EventChannel* ev_;
  int64_t t0_;
  std::atomic<bool> run_{false};
  std::thread th_;
};

}  // namespace hrc
