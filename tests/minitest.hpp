// SPDX-License-Identifier: MIT
// Minimal test harness (no third-party dependency).
#pragma once
#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

namespace minitest {
struct Case { const char* name; std::function<void()> fn; };
inline std::vector<Case>& cases() { static std::vector<Case> c; return c; }
inline int& failures() { static int f = 0; return f; }
struct Reg { Reg(const char* n, std::function<void()> f) { cases().push_back({n, std::move(f)}); } };
inline int run_all() {
  int failed_cases = 0;
  for (auto& c : cases()) {
    int before = failures();
    c.fn();
    bool ok = failures() == before;
    std::printf("[%s] %s\n", ok ? " OK " : "FAIL", c.name);
    failed_cases += !ok;
  }
  std::printf("%zu cases, %d failed\n", cases().size(), failed_cases);
  return failed_cases ? 1 : 0;
}
}  // namespace minitest

#define TEST(name) static void name(); static minitest::Reg reg_##name(#name, name); static void name()
#define CHECK(c) do { if (!(c)) { std::printf("  %s:%d CHECK(%s)\n", __FILE__, __LINE__, #c); ++minitest::failures(); } } while (0)
#define CHECK_NEAR(a, b, tol) do { double _a = (a), _b = (b); if (!(std::fabs(_a - _b) <= (tol))) { \
  std::printf("  %s:%d CHECK_NEAR(%s=%.9g, %s=%.9g, %g)\n", __FILE__, __LINE__, #a, _a, #b, _b, (double)(tol)); ++minitest::failures(); } } while (0)
