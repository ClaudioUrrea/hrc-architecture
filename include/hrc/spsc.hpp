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
//
// Release 3.1: the payload is held in an array of std::atomic<uint64_t> words and copied with
// relaxed atomic loads/stores, bracketed by the sequence counter and fences (H.-J. Boehm,
// "Can seqlocks get along with programming language memory models?", MSPC 2012, Sec. 4).
// Every shared access is atomic, so there is no data race under the C++17 memory model; the
// counter only decides whether a copy is consistent. Release 3.0 copied a plain payload with
// memcpy while the writer could be writing it, which is a data race (undefined behaviour)
// even though the counter detected the torn copy (Reviewer 2, round 4).
template <class T>
class SeqlockSlot {
  static_assert(std::is_trivially_copyable<T>::value, "SeqlockSlot requires trivially copyable T");
  static_assert(std::atomic<uint64_t>::is_always_lock_free, "SeqlockSlot needs lock-free 64-bit atomics");
  static constexpr size_t kWords = (sizeof(T) + sizeof(uint64_t) - 1) / sizeof(uint64_t);

 public:
  SeqlockSlot() {
    for (auto& w : words_) w.store(0, std::memory_order_relaxed);
  }
  void store(const T& v) {
    uint64_t buf[kWords] = {};
    std::memcpy(buf, &v, sizeof(T));  // private copy, not shared
    const uint64_t s = seq_.load(std::memory_order_relaxed);
    seq_.store(s + 1, std::memory_order_relaxed);
    std::atomic_thread_fence(std::memory_order_release);  // odd counter is visible before any word
    for (size_t i = 0; i < kWords; ++i) words_[i].store(buf[i], std::memory_order_relaxed);
    seq_.store(s + 2, std::memory_order_release);          // words are visible before the even counter
  }
  bool load(T& out) const {
    uint64_t buf[kWords];
    for (int attempt = 0; attempt < 64; ++attempt) {
      const uint64_t s1 = seq_.load(std::memory_order_acquire);
      if (s1 & 1) continue;
      for (size_t i = 0; i < kWords; ++i) buf[i] = words_[i].load(std::memory_order_relaxed);
      std::atomic_thread_fence(std::memory_order_acquire);  // word loads complete before the re-check
      const uint64_t s2 = seq_.load(std::memory_order_relaxed);
      if (s1 == s2) {
        std::memcpy(&out, buf, sizeof(T));  // consistent snapshot, private buffer
        return s1 != 0;
      }
    }
    return false;
  }

 private:
  std::atomic<uint64_t> seq_{0};
  std::atomic<uint64_t> words_[kWords];
};

}  // namespace hrc
