// SPDX-License-Identifier: MIT
// Remote barrier-inference server. Runs on the inference device (e.g. a Jetson) and answers
// one UDP request per control cycle with h and its input gradient. compute_ns is measured
// from datagram receipt to reply send, so the client can separate transport from compute.
//
//   hrc_infer_server --weights models/cbf_ur5e.json [--port 47011] [--cpu N] [--fifo 80]
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstdio>
#include <string>

#include "hrc/common.hpp"
#include "hrc/infer_proto.hpp"
#include "hrc/rt.hpp"
#include "hrc/safety.hpp"

using namespace hrc;

int main(int argc, char** argv) {
  std::string weights;
  int port = 47011, cpu = -1, prio = 0;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string a = argv[i];
    if (a == "--weights") weights = argv[i + 1];
    else if (a == "--port") port = std::stoi(argv[i + 1]);
    else if (a == "--cpu") cpu = std::stoi(argv[i + 1]);
    else if (a == "--fifo") prio = std::stoi(argv[i + 1]);
  }
  Mlp mlp;
  std::string err;
  if (weights.empty() || !mlp.load(weights, err)) {
    std::fprintf(stderr, "cannot load weights: %s\n", err.c_str());
    return 2;
  }
  RtSettings rs;
  rs.policy = prio > 0 ? "fifo" : "other";
  rs.priority = prio;
  rs.cpu = cpu;
  RtApplied ap = apply_rt(rs);
  std::fprintf(stderr, "[infer] weights %s sha256 %s, rt %s\n", weights.c_str(), mlp.sha256().c_str(), ap.to_json().c_str());
  int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(static_cast<uint16_t>(port));
  a.sin_addr.s_addr = INADDR_ANY;
  if (::bind(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) { std::perror("bind"); return 2; }
  InferRequest rq;
  InferReply rp{};
  double grad[kInferMaxX];
  for (;;) {
    sockaddr_in from{};
    socklen_t fl = sizeof from;
    ssize_t n = ::recvfrom(fd, &rq, sizeof rq, 0, reinterpret_cast<sockaddr*>(&from), &fl);
    const int64_t t0 = mono_ns();
    if (n != static_cast<ssize_t>(sizeof rq) || rq.magic != kInferMagic || static_cast<int>(rq.nx) != mlp.input_dim()) continue;
    rp.magic = kInferMagic;
    rp.seq = rq.seq;
    rp.h = mlp.forward_grad(rq.x, grad);
    for (uint32_t i = 0; i < rq.nx; ++i) rp.grad[i] = grad[i];
    rp.compute_ns = mono_ns() - t0;
    ::sendto(fd, &rp, sizeof rp, 0, reinterpret_cast<sockaddr*>(&from), fl);
  }
}
