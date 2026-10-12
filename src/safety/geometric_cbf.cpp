// SPDX-License-Identifier: MIT
#include <algorithm>
#include <cmath>

#include "hrc/safety.hpp"

namespace hrc {

GeometricCbf::GeometricCbf(const DhParams& dh, const GeometricCbfParams& p) : kin_(dh), p_(p) {
  pairs_.reserve(256);
}

bool GeometricCbf::evaluate(const RobotState& rs, const HumanState& hs, ConstraintSet& out) {
  out.clear();
  if (!rs.valid || !hs.available) {
    out.trustworthy = false;
    last_min_sep_ = -1;
    return false;
  }
  kin_.update(rs.q);
  const auto& pts = kin_.points();
  const double r_link = kin_.params().link_radius;
  // Sensing-data age: each keypoint may have closed in by (approach speed bound) * age since
  // it was observed; the bound is the same one used for the human-motion term below.

  pairs_.clear();
  double best = 1e9;
  for (int j = 0; j < kKeypoints; ++j) {
    if (hs.conf[static_cast<size_t>(j)] < p_.min_keypoint_conf) continue;
    const Vec3& ph = hs.kp[static_cast<size_t>(j)];
    for (int i = 0; i < static_cast<int>(pts.size()); ++i) {
      double d = (pts[static_cast<size_t>(i)].p - ph).norm() - r_link;
      pairs_.push_back({d, i, j});
      if (d < best) { best = d; last_kp_ = ph; }
    }
  }
  last_min_sep_ = best;
  if (pairs_.empty()) {
    out.trustworthy = false;
    return false;
  }
  const int k = std::min<int>(p_.max_rows, static_cast<int>(pairs_.size()));
  std::partial_sort(pairs_.begin(), pairs_.begin() + k, pairs_.end(),
                    [](const Pair& a, const Pair& b) { return a.d < b.d; });

  std::array<Vec3, kMaxDof> J;
  const int n = rs.q.n;
  double vmax_link = 0;
  for (int r = 0; r < k; ++r) {
    const Pair& pr = pairs_[static_cast<size_t>(r)];
    const LinkPoint& lp = pts[static_cast<size_t>(pr.pi)];
    const Vec3& ph = hs.kp[static_cast<size_t>(pr.kj)];
    Vec3 diff = lp.p - ph;
    double dn = diff.norm();
    if (dn < 1e-9) continue;
    Vec3 nrm = diff * (1.0 / dn);
    kin_.point_jacobian(lp.p, lp.link, J);
    ConstraintRow& row = out.rows[static_cast<size_t>(out.n)];
    Vec3 vpt{};
    for (int jj = 0; jj < n; ++jj) {
      row.a[static_cast<size_t>(jj)] = nrm.dot(J[static_cast<size_t>(jj)]);
      vpt += J[static_cast<size_t>(jj)] * rs.qd[jj];
    }
    for (int jj = n; jj < kMaxDof; ++jj) row.a[static_cast<size_t>(jj)] = 0;
    vmax_link = std::max(vmax_link, vpt.norm());
    // Upper bound on the human approach speed along nrm (positive = closing).
    double approach;
    if (p_.motion.worst_case) {
      approach = p_.motion.v_max;
    } else if (!p_.motion.measured) {
      approach = p_.motion.v_bound;
    } else {
      // kp_vel is the keypoint velocity; nrm points from the keypoint to the robot, so a
      // keypoint moving towards the robot has a positive component along nrm.
      double meas = nrm.dot(hs.kp_vel[static_cast<size_t>(pr.kj)]);
      approach = std::min(p_.motion.v_max, std::max(0.0, meas) + p_.motion.v_margin);
    }
    row.h = pr.d - approach * age_s_ - p_.r_safety;
    // d/dt(dist) = nrm.(J qd) - nrm.v_h  >=  -kappa h   =>   a.qd >= -kappa h + nrm.v_h
    row.rhs = -p_.kappa * row.h + approach;
    out.h_min = std::min(out.h_min, row.h);
    ++out.n;
  }
  last_link_speed_ = vmax_link;
  out.trustworthy = true;
  return out.n > 0;
}

double GeometricCbf::link_speed(const Joints& qd) const {
  std::array<Vec3, kMaxDof> J;
  double vmax = 0;
  for (const auto& lp : kin_.points()) {
    kin_.point_jacobian(lp.p, lp.link, J);
    Vec3 v{};
    for (int j = 0; j < qd.n; ++j) v += J[static_cast<size_t>(j)] * qd[j];
    vmax = std::max(vmax, v.norm());
  }
  return vmax;
}

// ---------------------------------------------------------------------------- SSM
PsdTerms protective_separation(const SsmParams& p, double v_r, double t_age) {
  PsdTerms t;
  t.v_r = std::max(0.0, v_r);
  t.T_s = p.a_stop > 0 ? t.v_r / p.a_stop : 0;
  t.S_h = p.v_h * (p.T_r + t.T_s);
  t.S_r = t.v_r * p.T_r;
  t.S_s = p.a_stop > 0 ? t.v_r * t.v_r / (2 * p.a_stop) : 0;  // = v_r * T_s / 2
  t.S_age = (p.v_h + t.v_r) * std::max(0.0, t_age);
  t.total = t.S_h + t.S_r + t.S_s + p.C + p.Z_d + p.Z_r + t.S_age;
  return t;
}

double max_speed_for_separation(const SsmParams& p, double separation, double t_age) {
  // total(v) = v^2/(2a) + v (T_r + v_h/a + t_age) + (v_h T_r + v_h t_age + C + Z_d + Z_r)
  const double A = 1.0 / (2 * p.a_stop);
  const double B = p.T_r + p.v_h / p.a_stop + t_age;
  const double C0 = p.v_h * p.T_r + p.v_h * t_age + p.C + p.Z_d + p.Z_r - separation;
  if (C0 >= 0) return 0.0;
  return (-B + std::sqrt(B * B - 4 * A * C0)) / (2 * A);
}

// ---------------------------------------------------------------------------- QP filter
// Goldfarb-Idnani dual active-set method specialised to H = I: starts at the unconstrained
// minimiser qd_nom, adds the most violated constraint, drops constraints whose multiplier
// would turn negative, and terminates finitely with the exact projection or a proof of
// infeasibility. Sizes are tiny (n <= 7 variables, <= 46 rows), so dense algebra is used.
namespace {
bool solve_small(int q, double G[kMaxDof][kMaxDof], const double* rhs, double* out) {
  double A[kMaxDof][kMaxDof + 1];
  for (int i = 0; i < q; ++i) { for (int j = 0; j < q; ++j) A[i][j] = G[i][j]; A[i][q] = rhs[i]; }
  for (int c = 0; c < q; ++c) {
    int piv = c;
    for (int r = c + 1; r < q; ++r) if (std::fabs(A[r][c]) > std::fabs(A[piv][c])) piv = r;
    if (std::fabs(A[piv][c]) < 1e-12) return false;
    if (piv != c) for (int j = 0; j <= q; ++j) std::swap(A[c][j], A[piv][j]);
    for (int r = 0; r < q; ++r) {
      if (r == c) continue;
      const double f = A[r][c] / A[c][c];
      for (int j = c; j <= q; ++j) A[r][j] -= f * A[c][j];
    }
  }
  for (int i = 0; i < q; ++i) out[i] = A[i][q] / A[i][i];
  return true;
}
}  // namespace

QpResult QpFilter::solve(const Joints& qd_nom, const Joints& qd_max, const ConstraintSet* const* sets, int nsets,
                         Joints& qd_out, int max_iters, double tol) {
  constexpr int kMaxRows = 2 * kMaxConstraintRows + 2 * kMaxDof;
  const int n = qd_nom.n;
  // constraints in the form  c_i . x >= b_i
  double C[kMaxRows][kMaxDof];
  double b[kMaxRows];
  int m = 0;
  for (int s = 0; s < nsets; ++s) {
    const ConstraintSet* cs = sets[s];
    if (!cs) continue;
    for (int r = 0; r < cs->n && m < kMaxRows - 2 * kMaxDof; ++r) {
      for (int j = 0; j < n; ++j) C[m][j] = cs->rows[static_cast<size_t>(r)].a[static_cast<size_t>(j)];
      b[m] = cs->rows[static_cast<size_t>(r)].rhs;
      ++m;
    }
  }
  for (int j = 0; j < n; ++j) {
    for (int k = 0; k < n; ++k) { C[m][k] = (k == j) ? -1.0 : 0.0; C[m + 1][k] = (k == j) ? 1.0 : 0.0; }
    b[m] = -qd_max[j];      // -x_j >= -max
    b[m + 1] = -qd_max[j];  //  x_j >= -max
    m += 2;
  }
  double x[kMaxDof];
  for (int j = 0; j < n; ++j) x[j] = qd_nom[j];
  int act[kMaxDof];
  double u[kMaxDof];
  int q = 0;
  auto slack = [&](int i) { double s = -b[i]; for (int j = 0; j < n; ++j) s += C[i][j] * x[j]; return s; };
  QpResult res;
  int it = 0;
  bool infeasible = false;
  (void)tol;
  while (it < max_iters) {
    int p = -1;
    double worst = -1e-10;
    for (int i = 0; i < m; ++i) {
      bool in = false;
      for (int a = 0; a < q; ++a) in = in || act[a] == i;
      if (in) continue;
      double s = slack(i);
      if (s < worst) { worst = s; p = i; }
    }
    if (p < 0) break;  // all satisfied
    double up = 0;
    for (;;) {
      ++it;
      double r[kMaxDof] = {0}, z[kMaxDof];
      if (q > 0) {
        double G[kMaxDof][kMaxDof], rhs[kMaxDof];
        for (int a = 0; a < q; ++a) {
          rhs[a] = 0;
          for (int j = 0; j < n; ++j) rhs[a] += C[act[a]][j] * C[p][j];
          for (int c2 = 0; c2 < q; ++c2) {
            double g = 0;
            for (int j = 0; j < n; ++j) g += C[act[a]][j] * C[act[c2]][j];
            G[a][c2] = g;
          }
        }
        if (!solve_small(q, G, rhs, r)) { infeasible = true; break; }
      }
      for (int j = 0; j < n; ++j) {
        z[j] = C[p][j];
        for (int a = 0; a < q; ++a) z[j] -= C[act[a]][j] * r[a];
      }
      double zz = 0;
      for (int j = 0; j < n; ++j) zz += z[j] * z[j];
      double t1 = 1e300;
      int k = -1;
      for (int a = 0; a < q; ++a)
        if (r[a] > 1e-12 && u[a] / r[a] < t1) { t1 = u[a] / r[a]; k = a; }
      const double t2 = zz > 1e-14 ? -slack(p) / zz : 1e300;
      const double t = std::min(t1, t2);
      if (t >= 1e299) { infeasible = true; break; }
      if (t2 < 1e299) for (int j = 0; j < n; ++j) x[j] += t * z[j];
      for (int a = 0; a < q; ++a) u[a] -= t * r[a];
      up += t;
      if (t2 <= t1) {  // full step: p becomes active
        if (q < n) { act[q] = p; u[q] = up; ++q; }
        break;
      }
      // partial step: drop the blocking constraint k and retry with p
      for (int a = k; a < q - 1; ++a) { act[a] = act[a + 1]; u[a] = u[a + 1]; }
      --q;
      if (it >= max_iters) break;
    }
    if (infeasible) break;
  }
  for (int j = 0; j < n; ++j) qd_out[j] = x[j];
  double viol = 0;
  for (int i = 0; i < m; ++i) viol = std::max(viol, -slack(i));
  res.iters = it;
  res.max_violation = viol;
  res.feasible = !infeasible && viol <= 1e-6;
  return res;
}

}  // namespace hrc
