// SPDX-License-Identifier: MIT
// Wait-free single-producer/single-consumer ring and a seqlock "latest value" slot.
// Both are used on the real-time path, so neither allocates after construction.
#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <type_traits>
#include <vector>

namespace hrc {

template <class T>
class SpscRing {
  static_assert(std::is_trivially_copyable<T>::value, "SpscRing requires trivially copyable T");

 public:
  explicit SpscRing(size_t capacity_pow2) : buf_(capacity_pow2), mask_(capacity_pow2 - 1) {
    if (capacity_pow2 == 0 || (capacity_pow2 & mask_)) throw "SpscRing capacity must be a power of two";
  }
  bool push(const T& v) {
    const size_t h = head_.load(std::memory_order_relaxed);
    const size_t t = tail_.load(std::memory_order_acquire);
    if (h - t > mask_) { dropped_.fetch_add(1, std::memory_order_relaxed); return false; }
    buf_[h & mask_] = v;
    head_.store(h + 1, std::memory_order_release);
    return true;
  }
  bool pop(T& out) {
    const size_t t = tail_.load(std::memory_order_relaxed);
    const size_t h = head_.load(std::memory_order_acquire);
    if (t == h) return false;
    out = buf_[t & mask_];
    tail_.store(t + 1, std::memory_order_release);
    return true;
  }
  uint64_t dropped() const { return dropped_.load(std::memory_order_relaxed); }

 private:
  std::vector<T> buf_;
  size_t mask_;
  alignas(64) std::atomic<size_t> head_{0};
  alignas(64) std::atomic<size_t> tail_{0};
  alignas(64) std::atomic<uint64_t> dropped_{0};
};

// Single writer, many readers; readers never block the writer.
template <class T>
class SeqlockSlot {
  static_assert(std::is_trivially_copyable<T>::value, "SeqlockSlot requires trivially copyable T");

 public:
  void store(const T& v) {
    uint64_t s = seq_.load(std::memory_order_relaxed);
    seq_.store(s + 1, std::memory_order_relaxed);
    std::atomic_thread_fence(std::memory_order_release);
    std::memcpy(&data_, &v, sizeof(T));
    std::atomic_thread_fence(std::memory_order_release);
    seq_.store(s + 2, std::memory_order_release);
  }
  bool load(T& out) const {
    for (int attempt = 0; attempt < 64; ++attempt) {
      uint64_t s1 = seq_.load(std::memory_order_acquire);
      if (s1 & 1) continue;
      std::memcpy(&out, &data_, sizeof(T));
      std::atomic_thread_fence(std::memory_order_acquire);
      uint64_t s2 = seq_.load(std::memory_order_relaxed);
      if (s1 == s2) return s1 != 0;
    }
    return false;
  }

 private:
  std::atomic<uint64_t> seq_{0};
  T data_{};
};

}  // namespace hrc
