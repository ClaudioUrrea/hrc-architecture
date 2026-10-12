// SPDX-License-Identifier: MIT
#include "hrc/sim.hpp"

#include <pthread.h>
#include <sched.h>

#include <algorithm>
#include <cmath>
#include <cstring>

#include "hrc/common.hpp"

namespace hrc {

namespace {
uint64_t splitmix(uint64_t x) {
  x += 0x9e3779b97f4a7c15ULL;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}
uint64_t hkey(uint64_t a, uint64_t b, uint64_t c = 0, uint64_t d = 0) {
  return splitmix(splitmix(splitmix(splitmix(a) ^ b) ^ c) ^ d);
}
double u01(uint64_t h) { return static_cast<double>(h >> 11) * (1.0 / 9007199254740992.0); }
double gauss(uint64_t h) {
  double u1 = std::max(1e-12, u01(h)), u2 = u01(splitmix(h));
  return std::sqrt(-2 * std::log(u1)) * std::cos(2 * M_PI * u2);
}
// minimum-jerk interpolation, s in [0,1]
double mj(double s) {
  s = std::clamp(s, 0.0, 1.0);
  return s * s * s * (10 - 15 * s + 6 * s * s);
}
Vec3 lerp(const Vec3& a, const Vec3& b, double s) { return a + (b - a) * s; }
}  // namespace

// ============================================================================ SimRobot
SimRobot::SimRobot(const SimRobotParams& p) : p_(p), hist_(256) {
  RobotState s;
  s.q = p.q0;
  s.q.n = p.dh.n;
  s.qd.n = p.dh.n;
  s.valid = true;
  for (auto& h : hist_) h = s;
  Cmd c{};
  c.qd.n = p.dh.n;
  cmd_.store(c);
}

SimRobot::~SimRobot() { disconnect(); }

Result SimRobot::connect(const ConnectionConfig&) {
  if (running_) return Result::Ok;
  running_ = true;
  th_ = std::thread([this] { loop(); });
  return Result::Ok;
}

Result SimRobot::disconnect() {
  if (running_.exchange(false) && th_.joinable()) th_.join();
  return Result::Ok;
}

void SimRobot::loop() {
  const int64_t dt_ns = static_cast<int64_t>(1e9 / p_.rate_hz);
  const double dt = dt_ns * 1e-9;
  const int n = p_.dh.n;
  RobotState s = hist_[0];
  int64_t t = mono_ns();
  // pending commands for latency emulation
  std::vector<Cmd> pending;
  pending.reserve(64);
  Cmd active{};
  active.qd.n = n;
  Cmd last_seen{};
  while (running_) {
    t += dt_ns;
    sleep_until_mono(t);
    const int64_t now = mono_ns();
    const bool partitioned = now < partition_until_.load();
    Cmd c;
    if (cmd_.load(c) && c.t_ns != last_seen.t_ns) {
      last_seen = c;
      if (!partitioned) pending.push_back(c);
    }
    const int64_t lat = static_cast<int64_t>(p_.cmd_latency_ms * 1e6);
    while (!pending.empty() && now - pending.front().t_ns >= lat) {
      active = pending.front();
      pending.erase(pending.begin());
    }
    // Controller-side command timeout: no fresh command for 3 servo periods of the host
    // stream (60 ms at 50 Hz) -> controlled stop, as the vendor stream interfaces do.
    const bool stale = now - active.t_ns > 60'000'000LL;
    for (int j = 0; j < n; ++j) {
      const bool stopping = active.stop || stale || estop_;
      if (stopping) {
        // stop category 2 ramp: constant deceleration to standstill
        double amax = (active.stop && active.decel > 0) ? active.decel : p_.limits.qdd_max[j];
        if (estop_) amax = 4 * p_.limits.qdd_max[j];
        const double v = std::fabs(s.qd[j]) - amax * dt;
        s.qd[j] = v > 0 ? std::copysign(v, s.qd[j]) : 0.0;
      } else {
        const double target = active.qd[j] * override_.load();
        const double acc = std::clamp((target - s.qd[j]) / p_.tau_s, -p_.limits.qdd_max[j], p_.limits.qdd_max[j]);
        s.qd[j] = std::clamp(s.qd[j] + acc * dt, -p_.limits.qd_max[j], p_.limits.qd_max[j]);
      }
      s.q[j] = std::clamp(s.q[j] + s.qd[j] * dt, p_.limits.qmin[j], p_.limits.qmax[j]);
    }
    s.t_ns = now;
    s.seq = ++seq_;
    s.status_bits = (active.stop ? static_cast<uint32_t>(kStatusProtectiveStop) : 0u) | (estop_ ? static_cast<uint32_t>(kStatusEmergencyStop) : 0u);
    hist_head_ = (hist_head_ + 1) % hist_.size();
    hist_[hist_head_] = s;
    // publish the state that is state_latency old
    const int64_t slat = static_cast<int64_t>(p_.state_latency_ms * 1e6);
    size_t k = hist_head_;
    for (size_t i = 0; i < hist_.size(); ++i) {
      const RobotState& h = hist_[k];
      if (now - h.t_ns >= slat || i + 1 == hist_.size()) {
        if (!partitioned) {
          RobotState vis = h;
          vis.t_ns = now;  // reception time on the host
          vis.valid = true;
          visible_.store(vis);
        }
        break;
      }
      k = (k + hist_.size() - 1) % hist_.size();
    }
  }
}

Result SimRobot::getCurrentState(RobotState& out) {
  if (!running_) return Result::NotConnected;
  int f = comm_faults_.load();
  if (f > 0) {
    comm_faults_.fetch_sub(1);
    return Result::CommError;  // response failed validation (checksum/format/range)
  }
  return visible_.load(out) ? Result::Ok : Result::Timeout;
}

Result SimRobot::streamJointVelocity(const Joints& qd, double) {
  if (!running_) return Result::NotConnected;
  Cmd c{mono_ns(), qd, false, 0};
  cmd_.store(c);
  return Result::Ok;
}
Result SimRobot::setOverride(double f) {
  if (f < 0 || f > 1) return Result::InvalidArgument;
  override_ = f;
  return Result::Ok;
}
Result SimRobot::protectiveStop(double decel) {
  Cmd c{};
  c.t_ns = mono_ns();
  c.qd.n = p_.dh.n;
  c.stop = true;
  c.decel = decel;
  cmd_.store(c);
  return Result::Ok;
}
Result SimRobot::emergencyStop() { estop_ = true; return Result::Ok; }
Result SimRobot::resetFault() { estop_ = false; return Result::Ok; }
HealthStatus SimRobot::getHealthStatus() const {
  HealthStatus h;
  h.connected = running_;
  RobotState s;
  if (visible_.load(s)) { h.last_rx_ns = s.t_ns; h.status_bits = s.status_bits; }
  return h;
}
Result SimRobot::moveJoint(const Joints&, double) { return Result::Unsupported; }
void SimRobot::inject_partition(double seconds) { partition_until_ = mono_ns() + static_cast<int64_t>(seconds * 1e9); }
void SimRobot::inject_comm_faults(int n_calls) { comm_faults_ = n_calls; }

// ============================================================================ SimHuman
SimHuman::SimHuman(const HumanScriptParams& p) : p_(p) {}

void SimHuman::inject_lunge(double t0, double dur, const Vec3& target, double speed) {
  std::lock_guard<std::mutex> lk(mu_);
  lunges_.push_back({t0, dur, speed, target});
}

void SimHuman::keypoints(double t, std::array<Vec3, kKeypoints>& kp) const {
  // Scenario table: fraction of the cycle spent with the hand in the shared zone, and
  // walking-speed multiplier.
  double hold = 0.20, speed_mul = 1.0, zone_x = p_.shared_zone_x;
  if (p_.scenario == "screwdriving") hold = 0.45;
  else if (p_.scenario == "inspection") { hold = 0.55; zone_x -= 0.05; }
  else if (p_.scenario == "material_handling") hold = 0.15;
  else if (p_.scenario == "mixed") speed_mul = 1.3;
  const double T = p_.cycle_s;
  const uint64_t k = static_cast<uint64_t>(std::floor(t / T));
  const double tc = t - static_cast<double>(k) * T;
  const double jy = (u01(hkey(p_.seed, k, 1)) - 0.5) * 0.4;          // lateral zone offset
  const double jz = (u01(hkey(p_.seed, k, 2)) - 0.5) * 0.15;
  const double sm = (p_.scenario == "mixed") ? 0.6 + 0.6 * u01(hkey(p_.seed, k, 3)) : 1.0;
  (void)speed_mul;

  const Vec3 far{2.0, 0.3 * jy, 0}, bench{zone_x + 0.60, jy, 0};
  // phase boundaries (fractions of T)
  const double f_walk_in = 0.15 * sm, f_reach = 0.10, f_hold = hold, f_withdraw = 0.10, f_walk_out = 0.15 * sm;
  double a0 = 0, a1 = f_walk_in, a2 = a1 + f_reach, a3 = a2 + f_hold, a4 = a3 + f_withdraw, a5 = a4 + f_walk_out;
  const double s = tc / T;
  Vec3 base;
  double reach = 0;  // 0 = rest, 1 = hand at zone point
  if (s < a1) base = lerp(far, bench, mj((s - a0) / (a1 - a0)));
  else if (s < a2) { base = bench; reach = mj((s - a1) / (a2 - a1)); }
  else if (s < a3) { base = bench; reach = 1; }
  else if (s < a4) { base = bench; reach = 1 - mj((s - a3) / (a4 - a3)); }
  else if (s < a5) base = lerp(bench, far, mj((s - a4) / (a5 - a4)));
  else base = far;

  // body frame: facing -x (towards the robot at the origin)
  auto B = [&](double fx, double fy, double z) { return Vec3{base.x - fx, base.y - fy, z}; };
  kp[0] = B(0, 0, 1.70);   // head
  kp[1] = B(0, 0, 1.50);   // neck
  kp[2] = B(0, 0.20, 1.45);   // right shoulder (right side is -y in the facing frame -> +y here)
  kp[6] = B(0, -0.20, 1.45);  // left shoulder
  kp[10] = B(0, 0, 1.25);  // spine mid
  kp[11] = B(0, 0, 1.00);  // pelvis
  kp[12] = B(0, 0.10, 0.95); kp[16] = B(0, -0.10, 0.95);
  kp[13] = B(0.02, 0.10, 0.50); kp[17] = B(0.02, -0.10, 0.50);
  kp[14] = B(0, 0.10, 0.08); kp[18] = B(0, -0.10, 0.08);
  kp[15] = B(0.12, 0.10, 0.02); kp[19] = B(0.12, -0.10, 0.02);
  // arms
  const Vec3 zone{zone_x, jy, 0.90 + jz};
  auto arm = [&](int sh, int el, int wr, int ha, const Vec3& hand_target, double r) {
    Vec3 rest_hand = kp[static_cast<size_t>(sh)] + Vec3{-0.08, 0, -0.63};
    Vec3 hand = lerp(rest_hand, hand_target, r);
    Vec3 u = hand - kp[static_cast<size_t>(sh)];
    double L = std::max(1e-6, u.norm());
    Vec3 wr_p = hand - u * (0.08 / L);
    Vec3 el_p = lerp(kp[static_cast<size_t>(sh)], wr_p, 0.5) + Vec3{0, 0, -0.08 * (1 - r) - 0.04};
    kp[static_cast<size_t>(el)] = el_p; kp[static_cast<size_t>(wr)] = wr_p; kp[static_cast<size_t>(ha)] = hand;
  };
  arm(2, 3, 4, 5, zone, reach);
  arm(6, 7, 8, 9, zone + Vec3{0.15, -0.25, 0}, 0.5 * reach);

  // injected lunges override the right hand and forearm
  std::lock_guard<std::mutex> lk(mu_);
  for (const auto& L : lunges_) {
    if (t < L.t0 || t > L.t0 + L.dur) continue;
    Vec3 start = kp[5];
    Vec3 d = L.target - start;
    double dist = d.norm();
    double travel = std::min(dist, L.speed * (t - L.t0));
    if (dist > 1e-6) {
      Vec3 hand = start + d * (travel / dist);
      Vec3 shift = hand - kp[5];
      kp[5] = hand; kp[4] += shift; kp[3] += shift * 0.5;
    }
  }
}

// ============================================================================ cameras
SimCameraArray::SimCameraArray(const CameraParams& p, const SimHuman& human, int64_t t0_ns)
    : p_(p), human_(human), t0_(t0_ns), dead_until_(static_cast<size_t>(p.n)) {
  for (int c = 0; c < p.n; ++c) {
    double a = 2 * M_PI * c / p.n;
    pos_.push_back({p.ring_radius_m * std::cos(a), p.ring_radius_m * std::sin(a), p.height_m});
    dead_until_[static_cast<size_t>(c)] = 0;
  }
}

void SimCameraArray::inject_stream_timeout(int cam, double s) {
  dead_until_[static_cast<size_t>(cam % p_.n)] = mono_ns() + static_cast<int64_t>(s * 1e9);
}
void SimCameraArray::inject_confidence_drop(double s, double factor) {
  conf_factor_ = factor;
  conf_drop_until_ = mono_ns() + static_cast<int64_t>(s * 1e9);
}

bool SimCameraArray::latest(int c, int64_t now, CameraFrame& f) const {
  if (now < dead_until_[static_cast<size_t>(c)].load()) return false;
  const double period_ns = 1e9 / p_.fps;
  const double phase = period_ns * c / p_.n;  // cameras are not synchronised
  const double since = static_cast<double>(now - t0_) - p_.latency_ms * 1e6 - phase;
  if (since < 0) return false;
  const int64_t fr = static_cast<int64_t>(std::floor(since / period_ns));
  if (fr == f.frame) return true;  // caller already has it
  f.frame = fr;
  f.t_acq_ns = t0_ + static_cast<int64_t>(phase + fr * period_ns);
  f.t_avail_ns = f.t_acq_ns + static_cast<int64_t>(p_.latency_ms * 1e6);
  std::array<Vec3, kKeypoints> truth;
  human_.keypoints((f.t_acq_ns - t0_) * 1e-9, truth);
  const bool drop = now < conf_drop_until_.load();
  for (int k = 0; k < kKeypoints; ++k) {
    const uint64_t base = hkey(p_.seed, static_cast<uint64_t>(c), static_cast<uint64_t>(k), static_cast<uint64_t>(fr));
    const bool occl = u01(hkey(p_.seed, static_cast<uint64_t>(c), static_cast<uint64_t>(k), static_cast<uint64_t>(fr / 6) + 7777)) < p_.occlusion_prob;
    const double range = (truth[static_cast<size_t>(k)] - pos_[static_cast<size_t>(c)]).norm();
    double sigma = p_.sigma0_m * range + p_.sigma_quad * range * range;
    double conf = 0.75 + 0.25 * u01(splitmix(base + 3));
    if (occl) { sigma = 0.25; conf = 0.1 * u01(splitmix(base + 5)); }
    if (drop) conf *= conf_factor_.load();
    f.kp[static_cast<size_t>(k)] = truth[static_cast<size_t>(k)] +
                                   Vec3{gauss(base + 11) * sigma, gauss(base + 13) * sigma, gauss(base + 17) * sigma};
    f.conf[static_cast<size_t>(k)] = conf;
    f.sigma[static_cast<size_t>(k)] = sigma;
  }
  return true;
}

// ============================================================================ fusion
CameraFusion::CameraFusion(const FusionParams& p, const SimCameraArray& cams) : p_(p), cams_(cams) {}
CameraFusion::~CameraFusion() { stop(); }

bool CameraFusion::start() {
  if (run_) return true;
  run_ = true;
  th_ = std::thread([this] { loop(); });
  return true;
}
void CameraFusion::stop() {
  if (run_.exchange(false) && th_.joinable()) th_.join();
}
FusionStats CameraFusion::stats() const {
  std::lock_guard<std::mutex> lk(stats_mu_);
  return stats_;
}

void CameraFusion::loop() {
  if (p_.cpu >= 0) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(p_.cpu, &set);
    pthread_setaffinity_np(pthread_self(), sizeof set, &set);
  }
  const int nc = cams_.count();
  std::vector<CameraFrame> cache(static_cast<size_t>(nc));
  const int64_t period = static_cast<int64_t>(1e9 / p_.rate_hz);
  const int64_t timeout = static_cast<int64_t>(p_.stream_timeout_ms * 1e6);
  std::vector<double> hist_t;
  std::vector<std::array<Vec3, kKeypoints>> hist_kp;
  const int win = std::max(3, p_.vel_window);
  constexpr double kVelClip = 3.0;  // m/s
  int64_t t = mono_ns();
  uint32_t seq = 0;
  while (run_) {
    t += period;
    sleep_until_mono(t);
    const int64_t t_start = mono_ns();
    HumanState hs{};
    int alive = 0;
    int64_t oldest = INT64_MAX;
    std::vector<bool> fresh(static_cast<size_t>(nc));
    for (int c = 0; c < nc; ++c) {
      cams_.latest(c, t_start, cache[static_cast<size_t>(c)]);
      const CameraFrame& f = cache[static_cast<size_t>(c)];
      fresh[static_cast<size_t>(c)] = f.frame >= 0 && (t_start - f.t_avail_ns) <= timeout;
      if (fresh[static_cast<size_t>(c)]) { ++alive; oldest = std::min(oldest, f.t_acq_ns); }
    }
    hs.streams_alive = alive;
    hs.available = alive > 0;
    double conf_sum = 0;
    if (alive > 0) {
      for (int k = 0; k < kKeypoints; ++k) {
        // Observations below kMinObsConf (occluded joints) are used only if no camera sees the
        // keypoint well; if none does, the previous position is held and the confidence stays low.
        constexpr double kMinObsConf = 0.3;
        Vec3 acc{};
        double wsum = 0, cmax = 0;
        for (int pass = 0; pass < 2 && wsum == 0; ++pass) {
          for (int c = 0; c < nc; ++c) {
            if (!fresh[static_cast<size_t>(c)]) continue;
            const CameraFrame& f = cache[static_cast<size_t>(c)];
            const double cf = f.conf[static_cast<size_t>(k)];
            if (pass == 0 && cf < kMinObsConf) continue;
            double w = cf / (f.sigma[static_cast<size_t>(k)] * f.sigma[static_cast<size_t>(k)]);
            acc += f.kp[static_cast<size_t>(k)] * w;
            wsum += w;
            cmax = std::max(cmax, cf);
          }
          if (pass == 0 && wsum == 0 && !hist_kp.empty()) break;  // hold previous position
        }
        hs.kp[static_cast<size_t>(k)] = wsum > 0 ? acc * (1.0 / wsum)
                                                 : (hist_kp.empty() ? Vec3{} : hist_kp.back()[static_cast<size_t>(k)]);
        hs.conf[static_cast<size_t>(k)] = cmax;
        conf_sum += cmax;
      }
      hs.mean_conf = conf_sum / kKeypoints;
      hs.t_obs_ns = oldest;  // conservative: age is measured from the oldest contributing frame
      // Velocity: least-squares slope over the last `vel_window` fused estimates, each stamped
      // with the mean acquisition time of its contributing frames.
      double t_mean = 0;
      int nf = 0;
      for (int c = 0; c < nc; ++c) if (fresh[static_cast<size_t>(c)]) { t_mean += cache[static_cast<size_t>(c)].t_acq_ns * 1e-9; ++nf; }
      t_mean /= std::max(1, nf);
      if (hist_t.empty() || t_mean > hist_t.back() + 1e-6) {
        hist_t.push_back(t_mean);
        hist_kp.push_back(hs.kp);
        if (static_cast<int>(hist_t.size()) > win) { hist_t.erase(hist_t.begin()); hist_kp.erase(hist_kp.begin()); }
      }
      const size_t H = hist_t.size();
      if (H >= 3) {
        double tm = 0;
        for (double t : hist_t) tm += t;
        tm /= static_cast<double>(H);
        double stt = 0;
        for (double t : hist_t) stt += (t - tm) * (t - tm);
        for (int k = 0; k < kKeypoints; ++k) {
          Vec3 pm{};
          for (size_t i = 0; i < H; ++i) pm += hist_kp[i][static_cast<size_t>(k)];
          pm = pm * (1.0 / static_cast<double>(H));
          Vec3 sxt{};
          for (size_t i = 0; i < H; ++i) sxt += (hist_kp[i][static_cast<size_t>(k)] - pm) * (hist_t[i] - tm);
          Vec3 v = stt > 0 ? sxt * (1.0 / stt) : Vec3{};
          const double vn = v.norm();
          if (vn > kVelClip) v = v * (kVelClip / vn);  // physically implausible speeds are clipped
          hs.kp_vel[static_cast<size_t>(k)] = v;
        }
      }
    } else {
      hist_t.clear();
      hist_kp.clear();
      hs.t_obs_ns = 0;
    }
    hs.seq = ++seq;
    hs.t_pub_ns = mono_ns();
    slot_.store(hs);
    const int64_t exec = mono_ns() - t_start;
    std::lock_guard<std::mutex> lk(stats_mu_);
    stats_.exec_hist[static_cast<size_t>(std::min<int64_t>(FusionStats::kBins, exec / 10000))]++;
    stats_.publishes++;
  }
}

}  // namespace hrc
