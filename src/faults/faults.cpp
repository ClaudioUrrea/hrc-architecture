// SPDX-License-Identifier: MIT
#include "hrc/faults.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <random>

#include "hrc/common.hpp"

namespace hrc {

std::vector<Injection> make_schedule(const FaultCampaignParams& p, double T) {
  std::vector<Injection> out;
  if (!p.enabled) return out;
  std::mt19937_64 rng(p.seed);
  struct C { FaultCategory c; double rate; };
  const C cats[] = {
      {FaultCategory::SensorTimeout, p.rate_sensor_timeout},
      {FaultCategory::TrackingLoss, p.rate_tracking_loss},
      {FaultCategory::NetworkPartition, p.rate_network_partition},
      {FaultCategory::ComputationalOverrun, p.rate_overrun},
      {FaultCategory::HardwareCommunication, p.rate_hw_comm},
      {FaultCategory::MemoryAllocation, p.rate_memory},
      {FaultCategory::ConfigurationInconsistency, p.rate_config},
      {FaultCategory::ConstraintViolation, p.rate_constraint},
  };
  std::uniform_real_distribution<double> U(0, 1);
  for (const auto& c : cats) {
    const double lam = c.rate * p.rate_scale / 3600.0;  // per second
    if (lam <= 0) continue;
    std::vector<double> times;
    if (p.arrival == "clustered") {
      const double m = std::max(1.0, p.mean_cluster_size);
      std::exponential_distribution<double> gap(lam / m);
      std::poisson_distribution<int> kids(m - 1.0);  // 1 + Poisson(m-1) events per cluster: mean m
      std::exponential_distribution<double> off(1.0 / p.cluster_spread_s);
      for (double t = gap(rng); t < T; t += gap(rng)) {
        int k = 1 + kids(rng);
        double tt = t;
        for (int i = 0; i < k; ++i) { if (tt < T) times.push_back(tt); tt += off(rng); }
      }
    } else if (p.arrival == "weibull") {
      const double k = p.weibull_shape;
      const double scale = (1.0 / lam) / std::tgamma(1.0 + 1.0 / k);  // same mean inter-arrival
      std::weibull_distribution<double> w(k, scale);
      for (double t = w(rng); t < T; t += w(rng)) times.push_back(t);
    } else {
      std::exponential_distribution<double> e(lam);
      for (double t = e(rng); t < T; t += e(rng)) times.push_back(t);
    }
    for (double t : times) {
      Injection in;
      in.t_s = t;
      in.category = c.c;
      switch (c.c) {
        case FaultCategory::SensorTimeout: in.duration_s = 0.5 + 4.5 * U(rng); in.param = static_cast<int>(rng() % 6); break;
        case FaultCategory::TrackingLoss: in.duration_s = 0.3 + 2.7 * U(rng); break;
        case FaultCategory::NetworkPartition: in.duration_s = 0.5 + 2.5 * U(rng); break;
        case FaultCategory::ComputationalOverrun: in.param = 22 + static_cast<int>(rng() % 15); break;  // ms of extra work
        case FaultCategory::HardwareCommunication: in.param = 1 + static_cast<int>(rng() % 5); break;
        case FaultCategory::ConstraintViolation: in.duration_s = 0.6; break;
        default: break;
      }
      out.push_back(in);
    }
  }
  std::sort(out.begin(), out.end(), [](const Injection& a, const Injection& b) { return a.t_s < b.t_s; });
  return out;
}

void write_schedule_csv(const std::vector<Injection>& s, const std::string& path) {
  std::ofstream f(path);
  f << "index,t_s,category,duration_s,param\n";
  for (size_t i = 0; i < s.size(); ++i)
    f << i << "," << s[i].t_s << "," << to_string(s[i].category) << "," << s[i].duration_s << "," << s[i].param << "\n";
}

FaultInjector::FaultInjector(std::vector<Injection> s, InjectionTargets& t, EventChannel* ev, int64_t t0)
    : s_(std::move(s)), tg_(t), ev_(ev), t0_(t0) {}
FaultInjector::~FaultInjector() { stop(); }
void FaultInjector::start() {
  run_ = true;
  th_ = std::thread([this] { loop(); });
}
void FaultInjector::stop() {
  if (run_.exchange(false) && th_.joinable()) th_.join();
}

void FaultInjector::loop() {
  for (size_t i = 0; i < s_.size() && run_; ++i) {
    const Injection& in = s_[i];
    const int64_t when = t0_ + static_cast<int64_t>(in.t_s * 1e9);
    while (run_ && mono_ns() < when) std::this_thread::sleep_for(std::chrono::milliseconds(std::min<int64_t>(50, std::max<int64_t>(1, (when - mono_ns()) / 1000000))));
    if (!run_) break;
    bool applied = true;
    switch (in.category) {
      case FaultCategory::SensorTimeout: if (tg_.stream_timeout) tg_.stream_timeout(in.param, in.duration_s); else applied = false; break;
      case FaultCategory::TrackingLoss: if (tg_.confidence_drop) tg_.confidence_drop(in.duration_s); else applied = false; break;
      case FaultCategory::NetworkPartition: if (tg_.partition) tg_.partition(in.duration_s); else applied = false; break;
      case FaultCategory::ComputationalOverrun: tg_.overrun_ms = in.param; break;
      case FaultCategory::HardwareCommunication: if (tg_.comm_faults) tg_.comm_faults(in.param); else applied = false; break;
      case FaultCategory::MemoryAllocation: tg_.memory_fault = true; break;
      case FaultCategory::ConfigurationInconsistency: if (tg_.bad_config) tg_.bad_config(); else applied = false; break;
      case FaultCategory::ConstraintViolation: if (tg_.lunge) tg_.lunge(in.duration_s); else applied = false; break;
      default: applied = false;
    }
    if (ev_) ev_->emit(EventKind::FaultInjected, static_cast<uint8_t>(in.category), in.duration_s,
                       static_cast<int32_t>(i), applied ? "applied" : "no_target");
  }
}

}  // namespace hrc
