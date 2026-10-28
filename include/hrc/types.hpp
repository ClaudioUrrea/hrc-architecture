// SPDX-License-Identifier: MIT
// Core value types shared by every layer. No vendor header may be included here.
#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <string>

namespace hrc {

constexpr int kMaxDof = 7;      // UR5e: 6, KUKA iiwa: 7, ABB IRB 14000 arm: 7
constexpr int kKeypoints = 20;  // human skeleton keypoints used by fusion and the barrier

struct Vec3 {
  double x = 0, y = 0, z = 0;
  Vec3() = default;
  Vec3(double a, double b, double c) : x(a), y(b), z(c) {}
  Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
  Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
  Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
  Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
  double dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
  Vec3 cross(const Vec3& o) const { return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x}; }
  double norm() const { return std::sqrt(dot(*this)); }
};

struct Joints {
  std::array<double, kMaxDof> v{};
  int n = 6;
  double& operator[](int i) { return v[static_cast<size_t>(i)]; }
  double operator[](int i) const { return v[static_cast<size_t>(i)]; }
};

struct Pose {
  Vec3 p;
  std::array<double, 4> q{1, 0, 0, 0};  // w, x, y, z
};

enum class Result : uint8_t { Ok = 0, Timeout, Rejected, NotConnected, CommError, InvalidArgument, Unsupported };
const char* to_string(Result r);

// Robot state as delivered by an adapter. t_ns is CLOCK_MONOTONIC at reception on the host.
struct RobotState {
  int64_t t_ns = 0;
  uint32_t seq = 0;
  bool valid = false;
  Joints q, qd;
  Pose tcp;
  uint32_t status_bits = 0;  // vendor status mapped to StatusBit
};

enum StatusBit : uint32_t {
  kStatusProtectiveStop = 1u << 0,
  kStatusEmergencyStop = 1u << 1,
  kStatusFault = 1u << 2,
  kStatusProgramRunning = 1u << 3,
};

// Fused human state. t_obs_ns: acquisition time of the oldest contributing frame;
// t_pub_ns: time the estimate was published into the lock-free slot.
struct HumanState {
  int64_t t_obs_ns = 0;
  int64_t t_pub_ns = 0;
  uint32_t seq = 0;
  bool available = false;
  int streams_alive = 0;
  double mean_conf = 0;
  std::array<Vec3, kKeypoints> kp{};
  std::array<Vec3, kKeypoints> kp_vel{};
  std::array<double, kKeypoints> conf{};
};

struct HealthStatus {
  bool connected = false;
  int32_t vendor_code = 0;
  uint32_t status_bits = 0;
  int64_t last_rx_ns = 0;
};

struct Limits {
  Joints qmin, qmax, qd_max, qdd_max;
};

struct ConnectionConfig {
  std::string host = "127.0.0.1";
  int port = 0;
  int timeout_ms = 100;
  std::string options;  // adapter-specific, JSON text
};

}  // namespace hrc
