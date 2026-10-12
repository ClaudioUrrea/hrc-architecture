// SPDX-License-Identifier: MIT
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cmath>
#include <cstring>

#include "hrc/common.hpp"
#include "hrc/infer_proto.hpp"
#include "hrc/safety.hpp"

namespace hrc {

// ---------------------------------------------------------------------------- MLP
bool Mlp::load(const std::string& path, std::string& err) {
  try {
    sha_ = sha256_file(path);
    Json j = Json::parse_file(path);
    alpha_ = j["leaky_alpha"].num(0.01);
    out_scale = j["out_scale"].num(1.0);
    const Json& L = j["layers"];
    layers_.clear();
    for (size_t l = 0; l < L.size(); ++l) {
      MlpLayer ml;
      ml.out = static_cast<int>(L[l]["W"].size());
      ml.in = static_cast<int>(L[l]["W"][size_t(0)].size());
      ml.W.resize(static_cast<size_t>(ml.out * ml.in));
      ml.b.resize(static_cast<size_t>(ml.out));
      for (int o = 0; o < ml.out; ++o) {
        for (int i = 0; i < ml.in; ++i) ml.W[static_cast<size_t>(o * ml.in + i)] = L[l]["W"][size_t(o)][size_t(i)].num();
        ml.b[static_cast<size_t>(o)] = L[l]["b"][size_t(o)].num();
      }
      if (!layers_.empty() && layers_.back().out != ml.in) { err = "layer size mismatch"; return false; }
      layers_.push_back(std::move(ml));
    }
    if (layers_.empty() || layers_.back().out != 1) { err = "last layer must have one output"; return false; }
    const int nx = layers_.front().in;
    x_mean.assign(static_cast<size_t>(nx), 0.0);
    x_scale.assign(static_cast<size_t>(nx), 1.0);
    for (int i = 0; i < nx; ++i) {
      x_mean[static_cast<size_t>(i)] = j["x_mean"][size_t(i)].num(0);
      x_scale[static_cast<size_t>(i)] = j["x_scale"][size_t(i)].num(1);
    }
    act_.assign(layers_.size() + 1, {});
    pre_.assign(layers_.size(), {});
    act_[0].resize(static_cast<size_t>(nx));
    size_t widest = static_cast<size_t>(nx);
    for (size_t l = 0; l < layers_.size(); ++l) {
      act_[l + 1].resize(static_cast<size_t>(layers_[l].out));
      pre_[l].resize(static_cast<size_t>(layers_[l].out));
      widest = std::max(widest, static_cast<size_t>(layers_[l].out));
    }
    gbuf_a_.resize(widest);
    gbuf_b_.resize(widest);
    return true;
  } catch (const std::exception& e) {
    err = e.what();
    return false;
  }
}

double Mlp::forward_grad(const double* x, double* grad_x) {
  const int nx = input_dim();
  for (int i = 0; i < nx; ++i) act_[0][static_cast<size_t>(i)] = (x[i] - x_mean[static_cast<size_t>(i)]) / x_scale[static_cast<size_t>(i)];
  const size_t L = layers_.size();
  for (size_t l = 0; l < L; ++l) {
    const MlpLayer& ly = layers_[l];
    const double* a = act_[l].data();
    for (int o = 0; o < ly.out; ++o) {
      const double* w = &ly.W[static_cast<size_t>(o * ly.in)];
      double s = ly.b[static_cast<size_t>(o)];
      for (int i = 0; i < ly.in; ++i) s += w[i] * a[i];
      pre_[l][static_cast<size_t>(o)] = s;
      act_[l + 1][static_cast<size_t>(o)] = (l + 1 < L) ? (s > 0 ? s : alpha_ * s) : s;
    }
  }
  const double y = act_[L][0] * out_scale;
  if (grad_x) {
    // backprop d y / d x
    double* g = gbuf_a_.data();
    double* gn = gbuf_b_.data();
    g[0] = out_scale;
    for (size_t l = L; l-- > 0;) {
      const MlpLayer& ly = layers_[l];
      if (l + 1 < L)
        for (int o = 0; o < ly.out; ++o) g[o] *= (pre_[l][static_cast<size_t>(o)] > 0 ? 1.0 : alpha_);
      for (int i = 0; i < ly.in; ++i) gn[i] = 0;
      for (int o = 0; o < ly.out; ++o) {
        const double* w = &ly.W[static_cast<size_t>(o * ly.in)];
        for (int i = 0; i < ly.in; ++i) gn[i] += w[i] * g[o];
      }
      std::swap(g, gn);
    }
    for (int i = 0; i < nx; ++i) grad_x[i] = g[i] / x_scale[static_cast<size_t>(i)];
  }
  return y;
}

// ---------------------------------------------------------------------------- learned CBF
void LearnedCbf::build_input(const DhParams& dh, const RobotState& rs, const HumanState& hs, double* x) {
  int k = 0;
  for (int i = 0; i < dh.n; ++i) x[k++] = rs.q[i];
  for (int j = 0; j < kKeypoints; ++j) {
    Vec3 r = hs.kp[static_cast<size_t>(j)] - dh.base;
    x[k++] = r.x; x[k++] = r.y; x[k++] = r.z;
  }
}

LearnedCbf::LearnedCbf(const DhParams& dh, const LearnedCbfParams& p) : dh_(dh), p_(p) {
  ok_ = mlp_.load(p.weights_path, err_);
  if (ok_ && mlp_.input_dim() != dh.n + 3 * kKeypoints) {
    ok_ = false;
    err_ = "weights expect input dim " + std::to_string(mlp_.input_dim()) + ", robot gives " +
           std::to_string(dh.n + 3 * kKeypoints);
  }
  x_.resize(static_cast<size_t>(dh.n + 3 * kKeypoints));
  g_.resize(x_.size());
  if (ok_ && p.remote) {
    sock_ = ::socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(static_cast<uint16_t>(p.remote_port));
    inet_pton(AF_INET, p.remote_host.c_str(), &a.sin_addr);
    if (sock_ < 0 || ::connect(sock_, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) {
      ok_ = false;
      err_ = "cannot open UDP socket to inference server";
    }
  }
}

LearnedCbf::~LearnedCbf() {
  if (sock_ >= 0) ::close(sock_);
}

bool LearnedCbf::remote_eval(const double* x, int nx, double& h, double* grad) {
  InferRequest rq{};
  rq.magic = kInferMagic;
  rq.seq = ++seq_;
  rq.nx = static_cast<uint32_t>(nx);
  for (int i = 0; i < nx; ++i) rq.x[i] = x[i];
  if (::send(sock_, &rq, sizeof rq, 0) != static_cast<ssize_t>(sizeof rq)) return false;
  int64_t deadline = mono_ns() + static_cast<int64_t>(p_.remote_timeout_us) * 1000;
  InferReply rp{};
  for (;;) {
    int64_t left_ms = (deadline - mono_ns()) / 1000000;
    pollfd pfd{sock_, POLLIN, 0};
    int pr = ::poll(&pfd, 1, static_cast<int>(std::max<int64_t>(0, left_ms)) + 1);
    if (pr <= 0 || mono_ns() > deadline) return false;
    ssize_t r = ::recv(sock_, &rp, sizeof rp, 0);
    if (r == static_cast<ssize_t>(sizeof rp) && rp.magic == kInferMagic && rp.seq == rq.seq) break;  // stale replies skipped
  }
  h = rp.h;
  for (int i = 0; i < nx; ++i) grad[i] = rp.grad[i];
  timing_.remote_compute_ns = rp.compute_ns;
  return std::isfinite(h);
}

bool LearnedCbf::evaluate(const RobotState& rs, const HumanState& hs, ConstraintSet& out) {
  out.clear();
  trusted_ = false;
  timing_ = {};
  if (!ok_ || !rs.valid || !hs.available) { out.trustworthy = false; return false; }
  const int64_t t0 = mono_ns();
  build_input(dh_, rs, hs, x_.data());
  const int nx = static_cast<int>(x_.size());
  double h = 0;
  bool good;
  if (p_.remote) {
    timing_.remote = true;
    good = remote_eval(x_.data(), nx, h, g_.data());
    timing_.timeout = !good;
  } else {
    h = mlp_.forward_grad(x_.data(), g_.data());
    good = std::isfinite(h);
  }
  timing_.total_ns = mono_ns() - t0;
  last_h_ = good ? h : NAN;
  if (!good) { out.trustworthy = false; return false; }
  // Gray zone: the model abstains; the geometric rows govern this cycle.
  if (std::fabs(h) < p_.gray_band) { out.trustworthy = false; out.h_min = h; return false; }

  ConstraintRow& row = out.rows[0];
  const int n = dh_.n;
  for (int j = 0; j < kMaxDof; ++j) row.a[static_cast<size_t>(j)] = j < n ? g_[static_cast<size_t>(j)] : 0.0;
  // Human term: dh/dt includes sum_k (dh/dp_k . v_k).
  // Human term. Measured keypoint velocities enter exactly; the uncertainty margin is applied
  // as a common-mode velocity of the whole body (|sum_k g_k| v_margin). The worst case lets
  // every keypoint move independently at v_max (v_max * sum_k |g_k|).
  double meas = 0, gnorm = 0;
  Vec3 gsum{};
  for (int k = 0; k < kKeypoints; ++k) {
    Vec3 gk{g_[static_cast<size_t>(n + 3 * k)], g_[static_cast<size_t>(n + 3 * k + 1)], g_[static_cast<size_t>(n + 3 * k + 2)]};
    meas += gk.dot(hs.kp_vel[static_cast<size_t>(k)]);
    gnorm += gk.norm();
    gsum += gk;
  }
  const double worst = p_.motion.v_max * gnorm;
  double bound;
  if (p_.motion.worst_case) bound = worst;
  else if (!p_.motion.measured) bound = p_.motion.v_bound * gsum.norm();   // common-mode body motion at v_bound
  else bound = std::min(worst, std::max(0.0, -meas) + p_.motion.v_margin * gsum.norm());
  row.h = h;
  row.rhs = -p_.kappa * h + bound;
  out.n = 1;
  out.h_min = h;
  out.trustworthy = true;
  trusted_ = true;
  return true;
}

}  // namespace hrc
