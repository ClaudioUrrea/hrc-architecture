// SPDX-License-Identifier: MIT
#include "hrc/kinematics.hpp"

#include <cmath>
#include <stdexcept>

#include "hrc/common.hpp"

namespace hrc {

DhParams DhParams::ur5e() {
  // Universal Robots, "DH parameters for calculations of kinematics and dynamics" (UR5e).
  DhParams p;
  p.model = "UR5e";
  p.n = 6;
  p.d = {0.1625, 0, 0, 0.1333, 0.0997, 0.0996, 0};
  p.a = {0, -0.425, -0.3922, 0, 0, 0, 0};
  p.alpha = {M_PI / 2, 0, 0, M_PI / 2, -M_PI / 2, 0, 0};
  p.link_radius = 0.06;
  return p;
}

DhParams DhParams::from_json_file(const std::string& path) {
  Json j = Json::parse_file(path);
  DhParams p;
  p.model = j["model"].str();
  p.n = static_cast<int>(j["dof"].i64(6));
  if (p.n < 1 || p.n > kMaxDof) throw std::runtime_error("dh: bad dof in " + path);
  for (int i = 0; i < p.n; ++i) {
    p.a[i] = j["a"][i].num();
    p.d[i] = j["d"][i].num();
    p.alpha[i] = j["alpha"][i].num();
    p.theta_offset[i] = j["theta_offset"][i].num(0);
  }
  p.link_radius = j["link_radius"].num(0.06);
  p.samples_per_link = static_cast<int>(j["samples_per_link"].i64(4));
  p.base = {j["base"][size_t(0)].num(0), j["base"][size_t(1)].num(0), j["base"][size_t(2)].num(0)};
  return p;
}

Kinematics::Kinematics(const DhParams& p) : p_(p) {
  pts_.reserve(static_cast<size_t>(p.n * (p.samples_per_link + 1) + 1));
}

void Kinematics::update(const Joints& q) {
  // R: rotation of frame i in base, stored as three column vectors
  Vec3 X{1, 0, 0}, Y{0, 1, 0}, Z{0, 0, 1};
  Vec3 o = p_.base;
  o_[0] = o;
  z_[0] = Z;
  for (int i = 0; i < p_.n; ++i) {
    const double th = q[i] + p_.theta_offset[i];
    const double ct = std::cos(th), st = std::sin(th), ca = std::cos(p_.alpha[i]), sa = std::sin(p_.alpha[i]);
    // T_i = Rz(th) Tz(d) Tx(a) Rx(alpha), applied in the current frame
    Vec3 Xn = X * ct + Y * st;
    Vec3 Yn = (X * (-st) + Y * ct) * ca + Z * sa;
    Vec3 Zn = (X * (-st) + Y * ct) * (-sa) + Z * ca;
    o = o + Z * p_.d[i] + Xn * p_.a[i];
    X = Xn; Y = Yn; Z = Zn;
    o_[static_cast<size_t>(i + 1)] = o;
    z_[static_cast<size_t>(i + 1)] = Z;
  }
  pts_.clear();
  const int k = std::max(1, p_.samples_per_link);
  for (int i = 0; i < p_.n; ++i) {
    const Vec3& A = o_[static_cast<size_t>(i)];
    const Vec3& B = o_[static_cast<size_t>(i + 1)];
    if ((B - A).norm() < 1e-6) continue;
    for (int s = 1; s <= k; ++s) {
      double t = static_cast<double>(s) / k;
      pts_.push_back({A + (B - A) * t, i + 1});
    }
  }
}

void Kinematics::point_jacobian(const Vec3& p, int link, std::array<Vec3, kMaxDof>& out) const {
  for (int j = 0; j < p_.n; ++j) {
    if (j < link) out[static_cast<size_t>(j)] = z_[static_cast<size_t>(j)].cross(p - o_[static_cast<size_t>(j)]);
    else out[static_cast<size_t>(j)] = Vec3{};
  }
}

}  // namespace hrc
