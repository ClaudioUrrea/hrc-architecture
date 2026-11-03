// SPDX-License-Identifier: MIT
// Release 3.1 tests for the three defects identified by Reviewer 2 in round 4:
//   (1) speed limits applied after the barrier QP could invalidate a barrier row;
//   (2) the supervisor applied only the limits of the most severe mode;
//   (3) SeqlockSlot copied a shared plain payload with memcpy (data race).
// Linked against hrc_safety + hrc_core only (same isolation property as test_safety_isolated).
// The concurrency tests are also built with -fsanitize=thread (target test_r31_tsan).
#include <atomic>
#include <cmath>
#include <cstdio>
#include <random>
#include <thread>
#include <vector>

#include "hrc/safety.hpp"
#include "hrc/spsc.hpp"
#include "hrc/supervisor.hpp"
#include "minitest.hpp"

using namespace hrc;

namespace {
Joints uniform(double v, int n = 6) {
  Joints j;
  j.n = n;
  for (int i = 0; i < n; ++i) j[i] = v;
  return j;
}
double row_slack(const ConstraintRow& r, const Joints& qd) {
  double ax = 0;
  for (int j = 0; j < qd.n; ++j) ax += r.a[static_cast<size_t>(j)] * qd[j];
  return ax - r.rhs;
}
}  // namespace

// ----------------------------------------------------------------------------- (1) composition
// The reviewer's example: kappa = 8, barrier value 0.05 m and approach-speed bound 0.6 m/s give
// a.qd >= -8*0.05 + 0.6 = 0.20 m/s. A QP solution on that boundary, scaled by 0.5 (3.0), gives 0.10.
TEST(r31_reviewer_example_old_composition_violates_new_does_not) {
  const double kappa = 8, h = 0.05, approach = 0.6;
  ConstraintSet cs;
  cs.n = 1;
  cs.rows[0].a = {1, 0, 0, 0, 0, 0, 0};
  cs.rows[0].h = h;
  cs.rows[0].rhs = -kappa * h + approach;
  CHECK_NEAR(cs.rows[0].rhs, 0.20, 1e-12);
  const Joints nom = uniform(0.0), qd_max = uniform(1.0);
  QpFilter qp;
  const ConstraintSet* sets[1] = {&cs};
  Joints out;
  QpResult r = qp.solve(nom, qd_max, sets, 1, out);
  CHECK(r.feasible);
  CHECK_NEAR(out[0], 0.20, 1e-9);
  // release 3.0: scale after solving
  Joints old = out;
  for (int j = 0; j < old.n; ++j) old[j] *= 0.5;
  CHECK_NEAR(row_slack(cs.rows[0], old), -0.10, 1e-9);  // the row is violated by 0.10 m/s
  // release 3.1: the scale is inside the problem
  GeometricCbf geo(DhParams::ur5e(), GeometricCbfParams{});
  Joints cmd;
  LimitedFilterResult lf = limited_filter(qp, geo, nom, qd_max, 0.5, -1.0, &cs, nullptr, cmd);
  CHECK(!lf.stop);
  CHECK(row_slack(cs.rows[0], cmd) >= -1e-9);
  CHECK(std::fabs(cmd[0]) <= 0.5 + 1e-12);
  const ConstraintSet* chk[2] = {&cs, nullptr};
  CHECK(command_violation(geo, cmd, qd_max, 0.5, -1.0, chk, 2) <= 1e-6);
}

TEST(r31_incompatible_speed_and_barrier_is_an_explicit_stop) {
  // the row needs 0.8 rad/s along joint 0; the reduced mode allows 0.5 -> conflict, stop
  ConstraintSet cs;
  cs.n = 1;
  cs.rows[0].a = {1, 0, 0, 0, 0, 0, 0};
  cs.rows[0].rhs = 0.8;
  GeometricCbf geo(DhParams::ur5e(), GeometricCbfParams{});
  QpFilter qp;
  Joints cmd;
  LimitedFilterResult lf = limited_filter(qp, geo, uniform(0.0), uniform(1.0), 0.5, -1.0, &cs, nullptr, cmd);
  CHECK(lf.stop);
  CHECK(lf.limit_conflict);
  CHECK(!lf.qp_failed);
  // at full speed it is feasible: not a conflict
  lf = limited_filter(qp, geo, uniform(0.0), uniform(1.0), 1.0, -1.0, &cs, nullptr, cmd);
  CHECK(!lf.stop);
  // infeasible even at full speed: qp_failed, not a conflict
  cs.rows[0].rhs = 1.5;
  lf = limited_filter(qp, geo, uniform(0.0), uniform(1.0), 0.5, -1.0, &cs, nullptr, cmd);
  CHECK(lf.stop && lf.qp_failed && !lf.limit_conflict);
}

// Randomised property: whatever the rows, the mode scale and the SSM limit, a command that the
// limited filter does not turn into a stop satisfies every row, the reduced box and the SSM
// limit. The same problems are also passed through the 3.0 composition to show that the
// property failed there.
TEST(r31_random_problems_dispatched_command_satisfies_all_limits) {
  std::mt19937 rng(31);
  std::uniform_real_distribution<double> U(-1, 1), Uq(-2.5, 2.5), U01(0, 1);
  GeometricCbf geo(DhParams::ur5e(), GeometricCbfParams{});
  QpFilter qp;
  const double scales[4] = {1.0, 0.7, 0.5, 0.5};
  int n_ok = 0, n_stop = 0, n_ssm = 0, old_viol = 0, new_viol = 0;
  for (int trial = 0; trial < 20000; ++trial) {
    Joints q = uniform(0.0);
    for (int j = 0; j < 6; ++j) q[j] = Uq(rng);
    geo.kinematics().update(q);
    ConstraintSet cs;
    cs.n = 1 + static_cast<int>(U01(rng) * 6);
    for (int r = 0; r < cs.n; ++r) {
      double nn = 0;
      for (int j = 0; j < 6; ++j) { cs.rows[static_cast<size_t>(r)].a[static_cast<size_t>(j)] = U(rng); nn += std::pow(cs.rows[static_cast<size_t>(r)].a[static_cast<size_t>(j)], 2); }
      for (int j = 0; j < 6; ++j) cs.rows[static_cast<size_t>(r)].a[static_cast<size_t>(j)] /= std::sqrt(nn);
      cs.rows[static_cast<size_t>(r)].rhs = 0.6 * U(rng);  // both signs: rhs > 0 means "move away"
    }
    Joints nom = uniform(0.0), qd_max = uniform(1.0);
    for (int j = 0; j < 6; ++j) nom[j] = U(rng);
    const double s = scales[trial % 4];
    const double v_ok = (trial % 3 == 0) ? -1.0 : 0.05 + 1.0 * U01(rng);
    Joints cmd;
    LimitedFilterResult lf = limited_filter(qp, geo, nom, qd_max, s, v_ok, &cs, nullptr, cmd);
    const ConstraintSet* chk[2] = {&cs, nullptr};
    if (lf.stop) { ++n_stop; }
    else {
      ++n_ok;
      if (lf.ssm_reduced) ++n_ssm;
      if (command_violation(geo, cmd, qd_max, s, v_ok, chk, 2) > 1e-6) ++new_viol;
    }
    // release 3.0: QP at full box, then scale by s and by the SSM ratio
    Joints full;
    QpResult r0 = qp.solve(nom, qd_max, chk, 1, full);
    if (r0.feasible) {
      double sc = s;
      if (v_ok >= 0) { const double v = geo.link_speed(full) * sc; if (v > v_ok) sc *= v_ok / v; }
      for (int j = 0; j < 6; ++j) full[j] *= sc;
      double worst = 0;
      for (int r = 0; r < cs.n; ++r) worst = std::max(worst, -row_slack(cs.rows[static_cast<size_t>(r)], full));
      if (worst > 1e-6) ++old_viol;
    }
  }
  std::printf("  random problems: %d dispatched (%d SSM-reduced), %d stops; violations: 3.1 = %d, 3.0 composition = %d\n",
              n_ok, n_ssm, n_stop, new_viol, old_viol);
  CHECK(new_viol == 0);
  CHECK(old_viol > 0);  // the defect reported by the reviewer is reproduced on the 3.0 composition
  CHECK(n_ok > 1000 && n_ssm > 100);
}

// ----------------------------------------------------------------------------- (2) supervisor
namespace {
struct SupDriver {
  Supervisor s{SupervisorParams{}};
  SupervisorInputs in;
  SupDriver() {
    in.now_ns = 1'000'000'000;
    in.robot_state_valid = in.estimate_available = true;
    in.streams_alive = in.streams_total = 6;
    in.mean_conf = 0.9;
    in.h_geo = 0.5;
    in.estimate_age_ns = 50'000'000;
  }
  Mode step(double dt_s = 0.02) { in.now_ns += static_cast<int64_t>(dt_s * 1e9); return s.update(in); }
  Mode run(double seconds) { Mode m = s.mode(); for (double t = 0; t < seconds; t += 0.02) m = step(); return m; }
};
}  // namespace

TEST(r31_low_confidence_plus_overrun_keeps_low_confidence_limits) {
  // Reviewer 2, round 4: 3.0 gave scale 1.0 / floor 0.15 m here; 3.1 must keep 0.7 / 0.225 m.
  SupDriver d;
  d.in.mean_conf = 0.5;
  CHECK(d.step() == Mode::LowConfidence);
  CHECK_NEAR(d.s.speed_scale(), 0.7, 0); CHECK_NEAR(d.s.floor(), 0.225, 0);
  d.in.previous_cycle_overrun = true;
  CHECK(d.step() == Mode::OverrunShed);        // reported mode: the most severe
  CHECK_NEAR(d.s.speed_scale(), 0.7, 0);        // limits: composed
  CHECK_NEAR(d.s.floor(), 0.225, 0);
  CHECK(d.s.active_mask() == ((1u << 1) | (1u << 4)));
  // clearing transition: overrun clears, low confidence still active
  d.in.previous_cycle_overrun = false;
  CHECK(d.step() == Mode::LowConfidence);
  CHECK_NEAR(d.s.speed_scale(), 0.7, 0); CHECK_NEAR(d.s.floor(), 0.225, 0);
  // low confidence clears after hold_clear_s
  d.in.mean_conf = 0.9;
  CHECK(d.run(1.1) == Mode::Nominal);
  CHECK_NEAR(d.s.speed_scale(), 1.0, 0); CHECK_NEAR(d.s.floor(), 0.15, 0);
  CHECK(d.s.active_mask() == 0);
}

TEST(r31_overrun_does_not_override_geometric_fallback) {
  SupDriver d;
  d.in.qp_relaxed = true;                      // learned barrier dropped -> fallback for fallback_hold_s
  CHECK(d.step() == Mode::GeometricFallback);
  d.in.qp_relaxed = false;
  CHECK_NEAR(d.s.speed_scale(), 0.5, 0); CHECK_NEAR(d.s.floor(), 0.30, 0);
  CHECK(!d.s.learned_allowed());
  d.in.previous_cycle_overrun = true;
  CHECK(d.step() == Mode::OverrunShed);
  CHECK_NEAR(d.s.speed_scale(), 0.5, 0); CHECK_NEAR(d.s.floor(), 0.30, 0);
  CHECK(!d.s.learned_allowed());               // 3.0 re-enabled the learned barrier here
  d.in.previous_cycle_overrun = false;
  CHECK(d.step() == Mode::GeometricFallback);
  CHECK(d.run(5.2) == Mode::Nominal);
  CHECK(d.s.learned_allowed());
}

TEST(r31_all_pairs_of_conditions_compose_conservatively) {
  // For every pair of the four non-stop conditions, the limits while both are active are at
  // least as restrictive as the limits of each one alone, and clearing either one restores
  // exactly the limits of the other.
  const SupervisorParams P{};
  auto raise = [](SupDriver& d, int k, bool on) {
    switch (k) {
      case 1: d.in.mean_conf = on ? 0.5 : 0.9; break;
      case 2: d.in.streams_alive = on ? 5 : 6; break;
      case 3: d.in.qp_relaxed = on; break;
      case 4: d.in.previous_cycle_overrun = on; break;
    }
  };
  for (int a = 1; a <= 4; ++a)
    for (int b = 1; b <= 4; ++b) {
      if (a == b) continue;
      SupDriver d;
      raise(d, a, true);
      d.step();
      raise(d, b, true);
      d.step();
      if (a == 3 || b == 3) d.in.qp_relaxed = false;  // the fallback hold keeps condition 3 active
      d.step();
      const double s_ab = d.s.speed_scale(), f_ab = d.s.floor();
      CHECK(s_ab <= std::min(P.speed_scale[static_cast<size_t>(a)], P.speed_scale[static_cast<size_t>(b)]) + 1e-12);
      CHECK(f_ab >= std::max(P.floor_m[static_cast<size_t>(a)], P.floor_m[static_cast<size_t>(b)]) - 1e-12);
      CHECK(d.s.mode() == static_cast<Mode>(std::max(a, b)));
      if (b == 4) {  // overrun clears on the next on-time cycle: the limits of `a` alone remain
        raise(d, 4, false);
        d.step();
        CHECK_NEAR(d.s.speed_scale(), P.speed_scale[static_cast<size_t>(a)], 0);
        CHECK_NEAR(d.s.floor(), P.floor_m[static_cast<size_t>(a)], 0);
      }
    }
}

TEST(r31_stop_dominates_and_clears_to_remaining_condition) {
  SupDriver d;
  d.in.mean_conf = 0.5;
  d.step();
  d.in.estimate_age_ns = 300'000'000;          // estimate too old -> protective stop
  CHECK(d.step() == Mode::ProtectiveStop);
  CHECK(d.s.stopped());
  CHECK_NEAR(d.s.speed_scale(), 0.0, 0);
  d.in.estimate_age_ns = 50'000'000;
  CHECK(d.run(1.1) == Mode::LowConfidence);    // resume_after_s elapsed; low confidence still active
  CHECK_NEAR(d.s.speed_scale(), 0.7, 0); CHECK_NEAR(d.s.floor(), 0.225, 0);
}

// ----------------------------------------------------------------------------- (3) data exchange
namespace {
struct Payload {             // 324 bytes, not a multiple of 8 on purpose
  uint64_t k;
  double v[39];
  uint32_t tail;
};
}  // namespace

TEST(r31_seqlock_concurrent_stress_no_torn_reads) {
  SeqlockSlot<Payload> slot;
  std::atomic<bool> run{true};
  std::atomic<uint64_t> torn{0}, reads{0}, backwards{0};
  std::thread writer([&] {
    Payload p{};
    for (uint64_t k = 1; run.load(std::memory_order_relaxed); ++k) {
      p.k = k;
      for (auto& x : p.v) x = static_cast<double>(k);
      p.tail = static_cast<uint32_t>(k);
      slot.store(p);
    }
  });
  std::vector<std::thread> readers;
  for (int r = 0; r < 3; ++r)
    readers.emplace_back([&] {
      Payload p{};
      uint64_t last = 0;
      while (run.load(std::memory_order_relaxed)) {
        if (!slot.load(p)) continue;
        reads.fetch_add(1, std::memory_order_relaxed);
        bool ok = p.tail == static_cast<uint32_t>(p.k);
        for (double x : p.v) ok = ok && x == static_cast<double>(p.k);
        if (!ok) torn.fetch_add(1, std::memory_order_relaxed);
        if (p.k < last) backwards.fetch_add(1, std::memory_order_relaxed);
        last = p.k;
      }
    });
  std::this_thread::sleep_for(std::chrono::seconds(3));
  run = false;
  writer.join();
  for (auto& t : readers) t.join();
  std::printf("  seqlock stress: %llu consistent reads, %llu torn, %llu out of order (3 readers, 1 writer, 3 s)\n",
              static_cast<unsigned long long>(reads.load()), static_cast<unsigned long long>(torn.load()),
              static_cast<unsigned long long>(backwards.load()));
  CHECK(reads.load() > 1000);
  CHECK(torn.load() == 0);
  CHECK(backwards.load() == 0);
}

TEST(r31_spsc_ring_concurrent_stress_in_order) {
  SpscRing<Payload> ring(1024);
  std::atomic<bool> done{false};
  const uint64_t N = 2'000'000;
  std::thread prod([&] {
    Payload p{};
    for (uint64_t k = 1; k <= N;) {
      p.k = k;
      p.tail = static_cast<uint32_t>(k);
      if (ring.push(p)) ++k;
    }
    done = true;
  });
  uint64_t expect = 1, bad = 0;
  Payload p{};
  while (expect <= N) {
    if (ring.pop(p)) {
      if (p.k != expect || p.tail != static_cast<uint32_t>(expect)) ++bad;
      ++expect;
    }
  }
  prod.join();
  std::printf("  spsc stress: %llu records, %llu out of order or torn, %llu push retries\n",
              static_cast<unsigned long long>(N), static_cast<unsigned long long>(bad),
              static_cast<unsigned long long>(ring.dropped()));
  CHECK(bad == 0);
}

int main() { return minitest::run_all(); }
