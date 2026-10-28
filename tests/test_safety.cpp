// SPDX-License-Identifier: MIT
// Safety-module tests. Linked against hrc_safety + hrc_core only: no adapter, no simulator,
// no protocol stack. That the binary links at all is the isolation property.
#include <cstdio>
#include <filesystem>
#include <random>

#include "hrc/common.hpp"
#include "hrc/control.hpp"
#include "hrc/kinematics.hpp"
#include "hrc/run_logger.hpp"
#include "hrc/safety.hpp"
#include "hrc/spsc.hpp"
#include "hrc/supervisor.hpp"
#include "minitest.hpp"

using namespace hrc;

TEST(sha256_known_vectors) {
  CHECK(sha256_hex("", 0) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  CHECK(sha256_hex("abc", 3) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  std::string m(1000, 'a');
  CHECK(sha256_hex(m.data(), m.size()) == "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3");
}

TEST(json_roundtrip) {
  Json j = Json::parse("{\"a\": 1.5, \"b\": [1, 2, 3], // comment\n \"c\": {\"d\": \"x\\ny\", \"e\": true}}");
  CHECK_NEAR(j["a"].num(), 1.5, 0);
  CHECK(j["b"].size() == 3);
  CHECK(j.get("c.d", std::string()) == "x\ny");
  CHECK(j.get_bool("c.e", false));
  CHECK_NEAR(j.get("c.missing", 7.0), 7.0, 0);
  Json k = Json::parse(j.dump());
  CHECK(k.get("c.d", std::string()) == "x\ny");
}

TEST(ur5e_zero_pose) {
  // Published UR5e zero configuration: TCP at (a2+a3, -(d4+d6), d1-d5)
  Kinematics k(DhParams::ur5e());
  Joints q; q.n = 6;
  k.update(q);
  Vec3 t = k.tcp();
  CHECK_NEAR(t.x, -0.8172, 1e-9);
  CHECK_NEAR(t.y, -0.2329, 1e-9);
  CHECK_NEAR(t.z, 0.0628, 1e-9);
}

TEST(point_jacobian_matches_finite_difference) {
  Kinematics k(DhParams::ur5e());
  std::mt19937 rng(3);
  std::uniform_real_distribution<double> U(-2, 2);
  for (int trial = 0; trial < 20; ++trial) {
    Joints q; q.n = 6;
    for (int i = 0; i < 6; ++i) q[i] = U(rng);
    k.update(q);
    auto pts = k.points();
    size_t pi = static_cast<size_t>(trial) % pts.size();
    std::array<Vec3, kMaxDof> J;
    k.point_jacobian(pts[pi].p, pts[pi].link, J);
    for (int j = 0; j < 6; ++j) {
      Joints qp = q;
      qp[j] += 1e-6;
      k.update(qp);
      Vec3 d = (k.points()[pi].p - pts[pi].p) * (1.0 / 1e-6);
      CHECK_NEAR(d.x, J[static_cast<size_t>(j)].x, 1e-5);
      CHECK_NEAR(d.y, J[static_cast<size_t>(j)].y, 1e-5);
      CHECK_NEAR(d.z, J[static_cast<size_t>(j)].z, 1e-5);
    }
  }
}

TEST(psd_constant_deceleration) {
  // Stopping distance under constant deceleration can never exceed v*T_s.
  SsmParams p;
  p.a_stop = 1.2;
  for (double v : {0.1, 0.3, 0.6, 1.0}) {
    PsdTerms t = protective_separation(p, v, 0.0);
    CHECK_NEAR(t.T_s, v / 1.2, 1e-12);
    CHECK_NEAR(t.S_s, v * t.T_s / 2, 1e-12);
    CHECK(t.S_s <= v * t.T_s + 1e-12);
  }
  // inversion
  for (double sep : {0.4, 0.8, 1.2, 2.0}) {
    double v = max_speed_for_separation(p, sep, 0.05);
    if (v > 0) CHECK_NEAR(protective_separation(p, v, 0.05).total, sep, 1e-9);
  }
  CHECK(max_speed_for_separation(p, 0.1, 0.0) == 0.0);
}

TEST(qp_unconstrained_returns_nominal) {
  QpFilter qp;
  Joints nom, mx, out;
  nom.n = mx.n = 6;
  for (int i = 0; i < 6; ++i) { nom[i] = 0.1 * i; mx[i] = 1.0; }
  ConstraintSet empty;
  const ConstraintSet* s[1] = {&empty};
  QpResult r = qp.solve(nom, mx, s, 1, out);
  CHECK(r.feasible);
  for (int i = 0; i < 6; ++i) CHECK_NEAR(out[i], nom[i], 1e-12);
}

TEST(qp_enforces_rows_and_is_minimal) {
  QpFilter qp;
  Joints nom, mx, out;
  nom.n = mx.n = 6;
  for (int i = 0; i < 6; ++i) { nom[i] = 0.5; mx[i] = 2.0; }
  ConstraintSet cs;
  cs.n = 1;
  cs.rows[0].a = {1, 1, 0, 0, 0, 0, 0};
  cs.rows[0].rhs = 2.0;  // q0 + q1 >= 2
  const ConstraintSet* s[1] = {&cs};
  QpResult r = qp.solve(nom, mx, s, 1, out);
  CHECK(r.feasible);
  CHECK_NEAR(out[0], 1.0, 1e-6);   // projection of (0.5,0.5) onto q0+q1=2
  CHECK_NEAR(out[1], 1.0, 1e-6);
  CHECK_NEAR(out[2], 0.5, 1e-9);
}

TEST(qp_reports_infeasible) {
  QpFilter qp;
  Joints nom, mx, out;
  nom.n = mx.n = 6;
  for (int i = 0; i < 6; ++i) mx[i] = 0.1;
  ConstraintSet cs;
  cs.n = 1;
  cs.rows[0].a = {1, 0, 0, 0, 0, 0, 0};
  cs.rows[0].rhs = 1.0;  // needs q0 >= 1 but |q0| <= 0.1
  const ConstraintSet* s[1] = {&cs};
  CHECK(!qp.solve(nom, mx, s, 1, out).feasible);
}


// Reference: Hildreth's dual coordinate ascent run to convergence on well-conditioned problems.
static void hildreth_ref(const std::vector<std::vector<double>>& C, const std::vector<double>& b, const std::vector<double>& x0,
                         std::vector<double>& x) {
  const size_t m = C.size(), n = x0.size();
  std::vector<double> lam(m, 0.0);
  for (int it = 0; it < 200000; ++it) {
    double ch = 0;
    for (size_t i = 0; i < m; ++i) {
      // constraint c.x >= b  <=>  -c.x <= -b ; x = x0 + sum lam_i c_i
      double cx = 0;
      for (size_t j = 0; j < n; ++j) {
        double xj = x0[j];
        for (size_t k = 0; k < m; ++k) xj += lam[k] * C[k][j];
        cx += C[i][j] * xj;
      }
      double cc = 0;
      for (size_t j = 0; j < n; ++j) cc += C[i][j] * C[i][j];
      double nl = std::max(0.0, lam[i] + (b[i] - cx) / cc);
      ch = std::max(ch, std::fabs(nl - lam[i]));
      lam[i] = nl;
    }
    if (ch < 1e-13) break;
  }
  x = x0;
  for (size_t k = 0; k < m; ++k) for (size_t j = 0; j < n; ++j) x[j] += lam[k] * C[k][j];
}

TEST(qp_matches_reference_on_random_problems) {
  std::mt19937 rng(17);
  std::normal_distribution<double> N(0, 1);
  QpFilter qp;
  int compared = 0;
  for (int trial = 0; trial < 200; ++trial) {
    Joints nom, mx, out;
    nom.n = mx.n = 6;
    for (int i = 0; i < 6; ++i) { nom[i] = N(rng); mx[i] = 3.0; }
    ConstraintSet cs;
    cs.n = 1 + trial % 6;
    std::vector<std::vector<double>> C;
    std::vector<double> b;
    for (int r = 0; r < cs.n; ++r) {
      std::vector<double> row(6);
      for (int j = 0; j < 6; ++j) { row[static_cast<size_t>(j)] = N(rng); cs.rows[static_cast<size_t>(r)].a[static_cast<size_t>(j)] = row[static_cast<size_t>(j)]; }
      cs.rows[static_cast<size_t>(r)].rhs = 0.3 * N(rng);
      C.push_back(row);
      b.push_back(cs.rows[static_cast<size_t>(r)].rhs);
    }
    const ConstraintSet* s[1] = {&cs};
    QpResult rr = qp.solve(nom, mx, s, 1, out);
    if (!rr.feasible) continue;
    bool box_active = false;
    for (int j = 0; j < 6; ++j) box_active = box_active || std::fabs(std::fabs(out[j]) - 3.0) < 1e-9;
    if (box_active) continue;  // reference below ignores the box
    std::vector<double> x0(nom.v.begin(), nom.v.begin() + 6), xr;
    hildreth_ref(C, b, x0, xr);
    for (int j = 0; j < 6; ++j) CHECK_NEAR(out[j], xr[static_cast<size_t>(j)], 1e-5);
    ++compared;
  }
  CHECK(compared > 150);
}

static HumanState human_at(const Vec3& p) {
  HumanState hs;
  hs.available = true;
  hs.streams_alive = 6;
  hs.mean_conf = 0.9;
  for (int k = 0; k < kKeypoints; ++k) { hs.kp[static_cast<size_t>(k)] = p + Vec3{0, 0, 0.05 * k}; hs.conf[static_cast<size_t>(k)] = 0.9; }
  return hs;
}

TEST(geometric_cbf_gradient_and_sign) {
  GeometricCbfParams gp;
  gp.motion.v_margin = 0;
  GeometricCbf g(DhParams::ur5e(), gp);
  RobotState rs;
  rs.valid = true;
  rs.q.n = rs.qd.n = 6;
  rs.q = Joints{{0.3, -1.2, 1.5, -1.8, -1.57, 0.0, 0}, 6};
  HumanState far = human_at({1.8, 0.0, 0.0});
  ConstraintSet cs;
  CHECK(g.evaluate(rs, far, cs));
  CHECK(cs.h_min > 0);
  // finite-difference check of the closest row's gradient
  double h0 = cs.rows[0].h;
  for (int j = 0; j < 6; ++j) {
    RobotState r2 = rs;
    r2.q[j] += 1e-6;
    ConstraintSet c2;
    g.evaluate(r2, far, c2);
    double fd = (c2.h_min - h0) / 1e-6;
    CHECK_NEAR(fd, cs.rows[0].a[static_cast<size_t>(j)], 1e-3);
  }
  HumanState near = human_at(g.kinematics().tcp());
  g.evaluate(rs, near, cs);
  CHECK(cs.h_min < 0);
}

TEST(data_age_tightens_barrier) {
  RobotState rs; rs.valid = true; rs.q.n = rs.qd.n = 6;
  HumanState hs = human_at({1.5, 0, 0});  // keypoints at rest
  for (bool worst : {false, true}) {
    GeometricCbfParams p;
    p.motion.worst_case = worst;
    p.motion.measured = !worst;
    GeometricCbf g(DhParams::ur5e(), p);
    ConstraintSet a, b;
    g.set_data_age(0.0);
    g.evaluate(rs, hs, a);
    g.set_data_age(0.1);
    g.evaluate(rs, hs, b);
    // worst case: v_max * age; measured (keypoints at rest): v_margin * age
    CHECK_NEAR(a.h_min - b.h_min, (worst ? p.motion.v_max : p.motion.v_margin) * 0.1, 1e-9);
  }
}

TEST(supervisor_priority_and_latching) {
  Supervisor s(SupervisorParams{});
  SupervisorInputs in;
  in.now_ns = 1'000'000'000;
  in.robot_state_valid = in.estimate_available = true;
  in.streams_alive = in.streams_total = 6;
  in.mean_conf = 0.9;
  in.h_geo = 0.5;
  in.estimate_age_ns = 50'000'000;
  CHECK(s.update(in) == Mode::Nominal);
  in.mean_conf = 0.5;  // low confidence AND one stream lost -> the more severe one wins
  in.streams_alive = 5;
  in.now_ns += 20'000'000;
  CHECK(s.update(in) == Mode::DegradedStream);
  in.mean_conf = 0.3;  // below the stop threshold -> protective stop dominates both
  in.now_ns += 20'000'000;
  CHECK(s.update(in) == Mode::ProtectiveStop);
  CHECK(s.speed_scale() == 0.0);
  in.mean_conf = 0.9; in.streams_alive = 6;
  for (int i = 0; i < 60; ++i) { in.now_ns += 20'000'000; s.update(in); }  // 1.2 s
  CHECK(s.mode() == Mode::DegradedStream || s.mode() == Mode::Nominal || s.mode() == Mode::LowConfidence);
  // constraint violation latches until acknowledged
  in.h_geo = -0.1;
  in.now_ns += 20'000'000;
  CHECK(s.update(in) == Mode::ProtectiveStopLatched);
  in.h_geo = 0.5;
  for (int i = 0; i < 400; ++i) { in.now_ns += 20'000'000; s.update(in); }
  CHECK(s.mode() == Mode::ProtectiveStopLatched);
  s.acknowledge(in.now_ns);
  in.now_ns += 20'000'000;
  CHECK(s.update(in) == Mode::Nominal);
}

TEST(supervisor_estimate_age_stops) {
  Supervisor s(SupervisorParams{});
  SupervisorInputs in;
  in.now_ns = 1'000'000'000;
  in.robot_state_valid = in.estimate_available = true;
  in.streams_alive = in.streams_total = 6;
  in.mean_conf = 0.9;
  in.h_geo = 0.5;
  in.estimate_age_ns = 300'000'000;  // older than estimate_hold_ms
  CHECK(s.update(in) == Mode::ProtectiveStop);
}

TEST(mlp_gradient_matches_finite_difference) {
  // write a small random network in the exported format, load it and check d y / d x
  std::mt19937 rng(5);
  std::normal_distribution<double> N(0, 0.4);
  const int nx = 66, h = 16;
  JsonWriter w;
  w.begin_object().kv("leaky_alpha", 0.01).kv("out_scale", 0.7);
  w.begin_array("x_mean"); for (int i = 0; i < nx; ++i) w.value(0.1 * (i % 3)); w.end_array();
  w.begin_array("x_scale"); for (int i = 0; i < nx; ++i) w.value(1.0 + 0.1 * (i % 5)); w.end_array();
  w.begin_array("layers");
  int dims[4] = {nx, h, h, 1};
  for (int l = 0; l < 3; ++l) {
    w.begin_object();
    w.begin_array("W");
    for (int o = 0; o < dims[l + 1]; ++o) { w.begin_array(); for (int i = 0; i < dims[l]; ++i) w.value(N(rng)); w.end_array(); }
    w.end_array();
    w.begin_array("b"); for (int o = 0; o < dims[l + 1]; ++o) w.value(N(rng)); w.end_array();
    w.end_object();
  }
  w.end_array().end_object();
  const std::string path = "/tmp/hrc_test_mlp.json";
  write_text_file(path, w.str());
  Mlp m;
  std::string err;
  CHECK(m.load(path, err));
  std::vector<double> x(nx), g(nx), g2(nx);
  for (auto& v : x) v = N(rng);
  double y = m.forward_grad(x.data(), g.data());
  for (int i = 0; i < nx; ++i) {
    auto xp = x;
    xp[static_cast<size_t>(i)] += 1e-6;
    double yp = m.forward_grad(xp.data(), g2.data());
    CHECK_NEAR((yp - y) / 1e-6, g[static_cast<size_t>(i)], 1e-4);
  }
  std::filesystem::remove(path);
}

TEST(spsc_ring_order_and_drops) {
  SpscRing<int> r(4);
  for (int i = 0; i < 6; ++i) r.push(i);
  CHECK(r.dropped() == 2);
  int v, expect = 0;
  while (r.pop(v)) CHECK(v == expect++);
  CHECK(expect == 4);
}

TEST(controller_compiles_against_interfaces_only) {
  // A nominal controller and the supervisor operate on interface types alone.
  Joints mx; mx.n = 6;
  for (int i = 0; i < 6; ++i) mx[i] = 1.0;
  JointPController c(mx);
  RobotState rs; rs.q.n = 6; rs.valid = true;
  Task t; t.q_goal.n = 6; t.q_goal[0] = 2.0;
  Joints qd;
  c.computeNominal(rs, t, qd);
  CHECK_NEAR(qd[0], 1.0, 1e-12);  // saturated
}

int main() { return minitest::run_all(); }
