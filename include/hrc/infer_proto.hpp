// SPDX-License-Identifier: MIT
// Wire format between the control host and the remote inference server (e.g. a Jetson).
// One UDP datagram each way, host byte order (both ends little-endian), fixed size.
#pragma once
#include <cstdint>

namespace hrc {

constexpr uint32_t kInferMagic = 0x48524331;  // "HRC1"
constexpr int kInferMaxX = 80;

#pragma pack(push, 1)
struct InferRequest {
  uint32_t magic;
  uint32_t seq;
  uint32_t nx;
  double x[kInferMaxX];
};
struct InferReply {
  uint32_t magic;
  uint32_t seq;
  int64_t compute_ns;   // server-side time from datagram receipt to reply send
  double h;
  double grad[kInferMaxX];
};
#pragma pack(pop)

}  // namespace hrc
