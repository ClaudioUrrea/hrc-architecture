# Build commands and compiler flags

## Executable used for the release-3.0 campaigns (round-3 manuscript)

Recorded from the build directory of the campaign machine (`build/CMakeCache.txt` and
`build/CMakeFiles/hrc_run.dir/flags.make`), not reconstructed:

| Item | Value |
|---|---|
| Host | Ubuntu 22.04.5 LTS under WSL2, kernel `PREEMPT_DYNAMIC` (not PREEMPT_RT) |
| Compiler | GNU 11.4.0 (`/usr/bin/c++`), CMake 3.22.1, Unix Makefiles |
| Configure | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` |
| Build | `make -C build -j` |
| Effective flags (`hrc_run`) | `-O2 -Wall -Wextra -Wpedantic -std=gnu++17` |
| Definitions | `-DHRC_BUILD_TYPE="Release" -DHRC_GIT_COMMIT="3d3d93d91fc8"` (stale label, see below) |
| `hrc_run` SHA-256 | `e3deadb08d7cd82f92f4ed45c60dbccd54b83fa60b10fa86728fbcd324b1e92d` (as in `PREREGISTRATION.md`) |

**Optimisation level.** `CMakeLists.txt` sets `CMAKE_CXX_FLAGS_RELEASE "-O2"`. The CMake cache
still lists the CMake default `-O3 -DNDEBUG` for that variable, but the value set in
`CMakeLists.txt` takes precedence, and `flags.make` confirms that `-O2` was used. Because the
CMake default is replaced, `NDEBUG` is not defined. The round-3 manuscript stated `-O3`; this was
an error in the text. `-march=native` is deliberately not used.

**Stale build label.** The binary was configured when HEAD was `3d3d93d`, so that is the
commit it embeds in every run manifest. It was rebuilt after the QP change without
re-running CMake. The sources at tag `campaign-v3` reproduce the binary's behaviour, and the
SHA-256 above links the executable to the deposited copy.

## Release 3.1

```bash
git checkout v3.1.0          # tag created when the configuration is frozen
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
make -C build -j8
ctest --test-dir build --output-on-failure
```

Effective flags are unchanged (`-O2 -Wall -Wextra -Wpedantic -std=gnu++17`). Each run
manifest records the embedded commit, which must match the tag with no `-dirty` suffix.

### Race detection (ThreadSanitizer)

```bash
cmake -S . -B build_tsan -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_CXX_FLAGS="-fsanitize=thread -g -O1"
make -C build_tsan -j8
for t in test_safety_isolated test_system test_r31; do
  TSAN_OPTIONS=halt_on_error=0 setarch "$(uname -m)" -R build_tsan/$t
done
```

`setarch -R` disables address-space randomisation for that process only. Without it,
ThreadSanitizer cannot map its shadow memory under the WSL2 kernel ("unexpected memory
mapping").

`tests/tsan_seqlock_probe.cpp` runs the writer/reader stress against whichever `spsc.hpp` is on
the include path. With GCC 11.4's ThreadSanitizer it produced **no report** for either the 3.0
header or the 3.1 header. A plain unsynchronised counter does produce a report in the same
environment. This dynamic check therefore cannot distinguish the 3.0 seqlock from the 3.1
seqlock. The 3.1 claim of race freedom rests on construction: every shared access in
`SeqlockSlot` is a `std::atomic` operation, following Boehm (MSPC 2012). The concurrent stress
tests and the clean ThreadSanitizer runs are supporting evidence, not a proof.
