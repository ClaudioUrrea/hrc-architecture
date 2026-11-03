cmake_minimum_required(VERSION 3.16)
project(hrc_architecture VERSION 3.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
add_compile_options(-Wall -Wextra -Wpedantic)
set(CMAKE_CXX_FLAGS_RELEASE "-O2")   # -march=native is deliberately not set: results must not depend on the build host

find_package(Threads REQUIRED)

# provenance of the binary, recorded in every run manifest
execute_process(COMMAND git rev-parse --short=12 HEAD WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
                OUTPUT_VARIABLE HRC_GIT OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
execute_process(COMMAND git status --porcelain WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
                OUTPUT_VARIABLE HRC_DIRTY OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT HRC_GIT)
  set(HRC_GIT "no-git")
endif()
if(HRC_DIRTY)
  set(HRC_GIT "${HRC_GIT}-dirty")
endif()
add_compile_definitions(HRC_GIT_COMMIT="${HRC_GIT}" HRC_BUILD_TYPE="${CMAKE_BUILD_TYPE}")

include_directories(${CMAKE_SOURCE_DIR}/include)

# ---------------------------------------------------------------- core (no vendor code)
add_library(hrc_core STATIC src/common/common.cpp src/log/run_logger.cpp src/kin/kinematics.cpp src/rt/rt.cpp)
target_link_libraries(hrc_core PUBLIC Threads::Threads)

# ---------------------------------------------------------------- safety + control: must build without any vendor SDK
add_library(hrc_safety STATIC src/safety/geometric_cbf.cpp src/safety/learned_cbf.cpp src/safety/limited_filter.cpp
            src/control/supervisor.cpp src/control/control.cpp)
target_link_libraries(hrc_safety PUBLIC hrc_core)

# ---------------------------------------------------------------- simulation backend
add_library(hrc_sim STATIC src/sim/sim.cpp)
target_link_libraries(hrc_sim PUBLIC hrc_core)

# ---------------------------------------------------------------- vendor adapters
add_library(hrc_adapters STATIC src/adapters/ur_rtde.cpp src/adapters/kuka_fri.cpp src/adapters/abb_egm.cpp
            src/ipc/socket_transport.cpp)
target_link_libraries(hrc_adapters PUBLIC hrc_core)

set(HRC_FRI_SDK_DIR "" CACHE PATH "KUKA FRI client SDK (C++) root; enables the KUKA adapter")
if(HRC_FRI_SDK_DIR)
  file(GLOB FRI_SRC ${HRC_FRI_SDK_DIR}/src/*/*.cpp ${HRC_FRI_SDK_DIR}/src/*.cpp)
  target_sources(hrc_adapters PRIVATE ${FRI_SRC})
  target_include_directories(hrc_adapters PRIVATE ${HRC_FRI_SDK_DIR}/include)
  target_compile_definitions(hrc_adapters PRIVATE HRC_HAVE_FRI)
  message(STATUS "KUKA FRI adapter: enabled (${HRC_FRI_SDK_DIR})")
else()
  message(STATUS "KUKA FRI adapter: disabled (set HRC_FRI_SDK_DIR)")
endif()

set(HRC_EGM_PROTO "" CACHE FILEPATH "egm.proto from RobotWare; enables the ABB EGM adapter")
if(HRC_EGM_PROTO)
  find_package(Protobuf REQUIRED)
  protobuf_generate_cpp(EGM_SRC EGM_HDR ${HRC_EGM_PROTO})
  target_sources(hrc_adapters PRIVATE ${EGM_SRC})
  target_include_directories(hrc_adapters PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
  target_link_libraries(hrc_adapters PRIVATE protobuf::libprotobuf)
  target_compile_definitions(hrc_adapters PRIVATE HRC_HAVE_EGM)
  message(STATUS "ABB EGM adapter: enabled")
else()
  message(STATUS "ABB EGM adapter: disabled (set HRC_EGM_PROTO)")
endif()

# ---------------------------------------------------------------- integration layer
add_library(hrc_integration STATIC src/integration/integration.cpp)
target_link_libraries(hrc_integration PUBLIC hrc_core)
find_package(open62541 QUIET)
if(open62541_FOUND)
  target_link_libraries(hrc_integration PRIVATE open62541::open62541)
  target_compile_definitions(hrc_integration PRIVATE HRC_HAVE_OPEN62541)
  message(STATUS "OPC-UA server: enabled (open62541)")
else()
  message(STATUS "OPC-UA server: disabled (open62541 not found)")
endif()

add_library(hrc_faults STATIC src/faults/faults.cpp)
target_link_libraries(hrc_faults PUBLIC hrc_core)

# ---------------------------------------------------------------- applications
add_executable(hrc_run apps/hrc_run.cpp)
target_link_libraries(hrc_run hrc_safety hrc_sim hrc_adapters hrc_integration hrc_faults)
add_executable(hrc_infer_server apps/hrc_infer_server.cpp)
target_link_libraries(hrc_infer_server hrc_safety)
add_executable(hrc_conformance apps/hrc_conformance.cpp)
target_link_libraries(hrc_conformance hrc_adapters)
add_executable(hrc_protocol_bench apps/hrc_protocol_bench.cpp)
target_link_libraries(hrc_protocol_bench hrc_core)

# release 3.1: Cartesian stopping check against Eq. (3) (tools/stop_samples.py feeds it)
add_executable(stop_check tools/stop_check.cpp)
target_link_libraries(stop_check hrc_core)

# ---------------------------------------------------------------- tests
enable_testing()
# The safety module is tested with NO adapter, simulator or integration library on the link line.
add_executable(test_safety_isolated tests/test_safety.cpp)
target_link_libraries(test_safety_isolated hrc_safety)
add_test(NAME safety_isolated COMMAND test_safety_isolated WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_executable(test_system tests/test_system.cpp)
target_link_libraries(test_system hrc_safety hrc_sim hrc_adapters hrc_integration hrc_faults)
add_test(NAME system COMMAND test_system WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
# release 3.1: composition of limits, supervisor with simultaneous conditions, concurrent data exchange.
# For race detection build the whole tree with -DCMAKE_CXX_FLAGS="-fsanitize=thread -g -O1" (docs/BUILD.md).
add_executable(test_r31 tests/test_r31.cpp)
target_link_libraries(test_r31 hrc_safety)
add_test(NAME r31_limits_supervisor_concurrency COMMAND test_r31 WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
