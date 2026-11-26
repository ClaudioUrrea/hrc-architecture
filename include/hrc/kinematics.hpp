// SPDX-License-Identifier: MIT
// Standard Denavit-Hartenberg forward kinematics and point Jacobians, used by the geometric
// barrier and by the built-in simulator. Parameter sets are data (cfg/robots/*.json); the
// values shipped for UR5e and KUKA LBR iiwa 7 R800 are the manufacturers' published DH
// tables, and the ABB entry must be verified by the user before use (see the file).
#pragma once
#include <array>
#include <string>
#include <vector>

#include "hrc/types.hpp"

namespace hrc {

struct DhParams {
  std::string model;
  int n = 6;
  std::array<double, kMaxDof> a{}, d{}, alpha{}, theta_offset{};
  double link_radius = 0.06;    // capsule radius used for separation (m)
  int samples_per_link = 4;     // points sampled along each link segment
  Vec3 base;                    // base position in the cell frame
  static DhParams from_json_file(const std::string& path);
  static DhParams ur5e();
};

struct LinkPoint {
  Vec3 p;
  int link = 0;  // number of joints that move this point (1..n)
};

class Kinematics {
 public:
  explicit Kinematics(const DhParams& p);
  // Computes joint-frame origins/axes and sampled link points for configuration q.
  void update(const Joints& q);
  const std::vector<LinkPoint>& points() const { return pts_; }
  // Translational Jacobian (3 x n, column-major in out[j]) of a point rigidly attached to `link`.
  void point_jacobian(const Vec3& p, int link, std::array<Vec3, kMaxDof>& out) const;
  Vec3 tcp() const { return o_[static_cast<size_t>(p_.n)]; }
  const DhParams& params() const { return p_; }

 private:
  DhParams p_;
  std::array<Vec3, kMaxDof + 1> o_{};
  std::array<Vec3, kMaxDof + 1> z_{};
  std::vector<LinkPoint> pts_;
};

}  // namespace hrc
