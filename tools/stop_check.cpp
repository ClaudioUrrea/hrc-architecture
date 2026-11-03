// SPDX-License-Identifier: MIT
// Cartesian stopping check (Reviewer 2, round 4): does a joint-space protective stop at
// `decel` rad/s^2 on every joint, after a reaction delay T_r, keep every sampled point of the
// UR5e within the stopping distance and time that Equation (3) assumes with a Cartesian
// deceleration a_stop?
//
//   stop_check --decel 3.0 --T_r 0.10 --a_stop 1.2 < samples.csv > per_sample.csv
//
// Input: one line per sample, "q1..q6,qd1..qd6" (rad, rad/s), taken from the cycle logs at the
// configurations and commanded speeds of the study. For each sample the stop is simulated at
// 1 kHz with the same per-joint constant-deceleration rule as the built-in simulator
// (src/sim/sim.cpp): the joint velocity is held for T_r (detection + command delay), then each
// joint decelerates independently at `decel` to standstill. For every link point the path
// length and the straight-line displacement are integrated; the worst point is compared with
//   v_r = largest link-point speed at stop onset,
//   S_eq3 = v_r*T_r + v_r^2/(2 a_stop)   (robot terms S_r + S_s of Eq. (3)),
//   T_eq3 = v_r / a_stop.
// Output columns: v_r, path_max, disp_max, S_eq3, t_stop (joint), T_eq3. A summary goes to stderr.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "hrc/kinematics.hpp"

using namespace hrc;

int main(int argc, char** argv) {
  double decel = 3.0, T_r = 0.10, a_stop = 1.2, dt = 1e-3;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string k = argv[i];
    double v = std::atof(argv[i + 1]);
    if (k == "--decel") decel = v;
    else if (k == "--T_r") T_r = v;
    else if (k == "--a_stop") a_stop = v;
    else if (k == "--dt") dt = v;
  }
  Kinematics kin(DhParams::ur5e());
  std::printf("v_r,path_max,disp_max,S_eq3,t_stop,T_eq3\n");
  char line[1024];
  long n = 0, n_path_exceeds = 0, n_disp_exceeds = 0, n_time_exceeds = 0;
  double worst_ratio_path = 0, worst_ratio_disp = 0, worst_ratio_time = 0;
  while (std::fgets(line, sizeof line, stdin)) {
    double x[12];
    int got = 0;
    char* p = line;
    while (got < 12) {
      char* e;
      x[got] = std::strtod(p, &e);
      if (e == p) break;
      ++got;
      p = e;
      while (*p == ',' || *p == ' ') ++p;
    }
    if (got < 12) continue;
    Joints q, qd;
    q.n = qd.n = 6;
    for (int j = 0; j < 6; ++j) { q[j] = x[j]; qd[j] = x[6 + j]; }
    kin.update(q);
    std::vector<Vec3> start, prev;
    for (const auto& lp : kin.points()) start.push_back(lp.p);
    prev = start;
    // onset speed of every point
    double v_r = 0;
    std::array<Vec3, kMaxDof> J;
    for (const auto& lp : kin.points()) {
      kin.point_jacobian(lp.p, lp.link, J);
      Vec3 v{};
      for (int j = 0; j < 6; ++j) v += J[static_cast<size_t>(j)] * qd[j];
      v_r = std::max(v_r, v.norm());
    }
    std::vector<double> path(start.size(), 0.0);
    double t = 0, t_stop = 0;
    bool moving = true;
    while (moving && t < 30) {
      t += dt;
      moving = false;
      for (int j = 0; j < 6; ++j) {
        if (t > T_r) {
          const double v = std::fabs(qd[j]) - decel * dt;
          qd[j] = v > 0 ? std::copysign(v, qd[j]) : 0.0;
        }
        q[j] += qd[j] * dt;
        moving = moving || qd[j] != 0.0;
      }
      kin.update(q);
      const auto& pts = kin.points();
      for (size_t i = 0; i < pts.size(); ++i) {
        path[i] += (pts[i].p - prev[i]).norm();
        prev[i] = pts[i].p;
      }
      if (moving) t_stop = t;
    }
    double path_max = 0, disp_max = 0;
    for (size_t i = 0; i < start.size(); ++i) {
      path_max = std::max(path_max, path[i]);
      disp_max = std::max(disp_max, (prev[i] - start[i]).norm());
    }
    const double S_eq3 = v_r * T_r + v_r * v_r / (2 * a_stop);
    const double T_eq3 = v_r / a_stop;
    const double t_brake = std::max(0.0, t_stop - T_r);
    std::printf("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n", v_r, path_max, disp_max, S_eq3, t_brake, T_eq3);
    ++n;
    if (S_eq3 > 1e-9) {
      n_path_exceeds += path_max > S_eq3 + 1e-9;
      n_disp_exceeds += disp_max > S_eq3 + 1e-9;
      worst_ratio_path = std::max(worst_ratio_path, path_max / S_eq3);
      worst_ratio_disp = std::max(worst_ratio_disp, disp_max / S_eq3);
    }
    if (T_eq3 > 1e-9) {
      n_time_exceeds += t_brake > T_eq3 + 1e-9;
      worst_ratio_time = std::max(worst_ratio_time, t_brake / T_eq3);
    }
  }
  std::fprintf(stderr,
               "samples=%ld decel=%.2f rad/s^2 T_r=%.3f s a_stop=%.2f m/s^2\n"
               "  path length > S_eq3: %ld (worst ratio %.3f)\n"
               "  displacement > S_eq3: %ld (worst ratio %.3f)\n"
               "  braking time > T_eq3: %ld (worst ratio %.3f)\n",
               n, decel, T_r, a_stop, n_path_exceeds, worst_ratio_path, n_disp_exceeds, worst_ratio_disp, n_time_exceeds,
               worst_ratio_time);
  return 0;
}
