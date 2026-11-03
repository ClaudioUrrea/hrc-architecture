// SPDX-License-Identifier: MIT
// Release 3.1: barrier QP with the supervisor speed scale and the SSM speed limit inside the
// problem (see safety.hpp). Replaces the post-QP scaling of release 3.0.
#include <algorithm>
#include <cmath>

#include "hrc/safety.hpp"

namespace hrc {

namespace {
QpResult solve_at(QpFilter& qp, double sigma, const Joints& qd_nom, const Joints& qd_max,
                  const ConstraintSet* const* sets, int nsets, Joints& out) {
  Joints box = qd_max, nom = qd_nom;
  for (int j = 0; j < box.n; ++j) { box[j] *= sigma; nom[j] *= sigma; }
  return qp.solve(nom, box, sets, nsets, out);
}
}  // namespace

LimitedFilterResult limited_filter(QpFilter& qp, const GeometricCbf& geo, const Joints& qd_nom, const Joints& qd_max,
                                   double s_mode, double v_ok, const ConstraintSet* geo_rows,
                                   const ConstraintSet* learned_rows, Joints& qd_out) {
  LimitedFilterResult res;
  const ConstraintSet* rows[2] = {geo_rows, learned_rows};
  Joints tmp = qd_out;
  tmp.n = qd_out.n = qd_nom.n;
  double sigma = std::clamp(s_mode, 0.0, 1.0);

  QpResult qr = solve_at(qp, sigma, qd_nom, qd_max, rows, 2, qd_out);
  res.iters += qr.iters;
  if (!qr.feasible && learned_rows) {
    // learned rows dropped, geometric rows kept (same rule as release 3.0)
    res.relaxed = true;
    rows[1] = nullptr;
    qr = solve_at(qp, sigma, qd_nom, qd_max, rows, 2, qd_out);
    res.iters += qr.iters;
  }
  if (!qr.feasible) {
    QpResult qf = solve_at(qp, 1.0, qd_nom, qd_max, rows, 2, tmp);
    res.iters += qf.iters;
    if (qf.feasible && sigma < 1.0) res.limit_conflict = true;
    else res.qp_failed = true;
    res.stop = true;
    return res;
  }
  if (v_ok >= 0) {
    const double v0 = geo.link_speed(qd_out);
    if (v0 > v_ok) {
      res.ssm_reduced = true;
      bool found = false;
      double cand = (v_ok > 1e-6 && v0 > 1e-9) ? sigma * v_ok / v0 : 0.0;
      for (int it = 0; it < 12; ++it) {
        if (it == 11) cand = 0.0;
        QpResult qs = solve_at(qp, cand, qd_nom, qd_max, rows, 2, tmp);
        res.iters += qs.iters;
        if (!qs.feasible && rows[1]) {
          // same rule as above: learned rows that make the problem infeasible are dropped
          const ConstraintSet* geo_only[2] = {rows[0], nullptr};
          qs = solve_at(qp, cand, qd_nom, qd_max, geo_only, 2, tmp);
          res.iters += qs.iters;
          if (qs.feasible) { res.relaxed = true; rows[1] = nullptr; }
        }
        if (qs.feasible && geo.link_speed(tmp) <= v_ok) { found = true; break; }
        if (cand == 0.0) break;
        cand *= 0.5;
      }
      if (!found) {  // the rows need motion that the SSM limit forbids
        res.limit_conflict = true;
        res.stop = true;
        return res;
      }
      qd_out = tmp;
      sigma = cand;
    }
  }
  res.sigma = sigma;
  return res;
}

double command_violation(const GeometricCbf& geo, const Joints& qd, const Joints& qd_max, double s_mode, double v_ok,
                         const ConstraintSet* const* sets, int nsets) {
  double viol = 0.0;
  for (int s = 0; s < nsets; ++s) {
    const ConstraintSet* cs = sets[s];
    if (!cs) continue;
    for (int r = 0; r < cs->n; ++r) {
      const ConstraintRow& row = cs->rows[static_cast<size_t>(r)];
      double ax = 0, an = 0;
      for (int j = 0; j < qd.n; ++j) {
        ax += row.a[static_cast<size_t>(j)] * qd[j];
        an += row.a[static_cast<size_t>(j)] * row.a[static_cast<size_t>(j)];
      }
      if (an > 1e-18) viol = std::max(viol, (row.rhs - ax) / std::sqrt(an));
    }
  }
  for (int j = 0; j < qd.n; ++j) viol = std::max(viol, std::fabs(qd[j]) - qd_max[j] * s_mode);
  if (v_ok >= 0) viol = std::max(viol, geo.link_speed(qd) - v_ok);
  return viol;
}

}  // namespace hrc
