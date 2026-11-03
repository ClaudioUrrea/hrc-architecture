// SPDX-License-Identifier: MIT
// hrc_run: executes one experiment run described by a JSON configuration and writes one raw
// run directory (see include/hrc/run_logger.hpp). Every number in the paper must be
// computable from such directories by the scripts in analysis/.
//
//   hrc_run --config cfg/timing_block.json [--variant block_001] [--duration 6000]
//           [--seed N] [--backup /path] [--run-root runs] [--notes "..."]
#include <signal.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <random>
#include <thread>
#include <vector>

#include "hrc/adapters.hpp"
#include "hrc/common.hpp"
#include "hrc/control.hpp"
#include "hrc/faults.hpp"
#include "hrc/integration.hpp"
#include "hrc/rt.hpp"
#include "hrc/run_logger.hpp"
#include "hrc/safety.hpp"
#include "hrc/sim.hpp"
#include "hrc/supervisor.hpp"

using namespace hrc;
namespace fs = std::filesystem;

static std::atomic<bool> g_stop{false};
static void on_signal(int) { g_stop = true; }

namespace {

Joints joints_from(const Json& a, int n) {
  Joints j;
  j.n = n;
  for (int i = 0; i < n; ++i) j[i] = a[static_cast<size_t>(i)].num(0);
  return j;
}

std::string usage() {
  return "usage: hrc_run --config FILE [--variant NAME] [--duration S] [--seed N] [--backup DIR]... "
         "[--run-root DIR] [--notes TEXT]\n";
}

// Evaluation-only ground truth (3.1), written by a probe thread on the auxiliary core and read
// by the control loop when it builds the cycle record. Never used for control.
struct GtSample {
  static constexpr int kRing = 8;
  int64_t t_gt_ns = 0;          // when the ground-truth separation was evaluated
  double sep = NAN;             // simulator robot state vs scripted human keypoints (m)
  int head = 0;
  int64_t t_obs[kRing] = {};    // observation times of the last fused estimates
  double err[kRing] = {};       // their largest keypoint error vs ground truth at that time (m)
  double err_closest[kRing] = {};  // error of their keypoint closest to the robot (m)
};

struct LoopContext {
  // configuration
  int64_t period_ns = 20'000'000;
  int64_t duration_ns = 0;
  Strategy strategy = Strategy::Proposed;
  bool learned_enabled = true;
  double learned_budget_ms = 5.0;
  double stop_decel_joint = 3.0;  // rad/s^2 for protective stops
  bool ssm_monitor = true;
  SsmParams ssm;
  PotentialFieldParams pf;
  Joints qd_max;
  // components
  ISensorFusion* fusion = nullptr;
  GeometricCbf* geo = nullptr;
  LearnedCbf* learned = nullptr;
  Supervisor* sup = nullptr;
  TaskSequencer* tasks = nullptr;
  IController* nominal = nullptr;
  RunLogger* log = nullptr;
  EventChannel* ev = nullptr;
  IntegrationBus* bus = nullptr;
  InjectionTargets* inj = nullptr;
  const SeqlockSlot<GtSample>* gt = nullptr;
  int streams_total = 0;
  // shared with other threads
  std::atomic<int64_t> heartbeat_ns{0};
  std::atomic<bool> running{false};
  std::atomic<int> mode{0};
  std::atomic<bool> ack_request{false};
  std::atomic<bool> config_rejected{false};
  // results
  uint64_t cycles = 0, deadline_misses = 0, injected_overrun_cycles = 0, late_releases = 0;
};

// The control loop. RobotT is IRobotController for the layered build and a concrete adapter
// type (static dispatch, no interface indirection) for the monolithic ablation variant A0.
template <class RobotT>
void control_loop(LoopContext& c, RobotT& robot) {
  QpFilter qp;
  RobotState rs;
  HumanState hs;
  Task task;
  task.q_goal.n = c.qd_max.n;
  Joints qd_nom, qd_cmd, qd_tmp;
  qd_nom.n = qd_cmd.n = qd_tmp.n = c.qd_max.n;
  ConstraintSet gset, lset;
  bool prev_overrun = false, qp_relaxed_prev = false, learned_failed_prev = false;
  bool ctrl_stop_prev = false;      // a controller-level stop (QP infeasible, limit conflict, final check) was active
  int32_t d_enqueue_prev = -1;      // enqueue duration of the previous record (logged in the next one)
  double last_override = -1;
  int64_t last_state_ns = 0;
  uint32_t last_state_seq = 0;

  const int64_t t_start = mono_ns();
  int64_t t_rel = (t_start / c.period_ns + 1) * c.period_ns;
  const int64_t t_end_run = t_start + c.duration_ns;
  c.running = true;
  c.heartbeat_ns = t_start;

  for (uint64_t idx = 0; !g_stop && (c.duration_ns <= 0 || t_rel < t_end_run); ++idx) {
    sleep_until_mono(t_rel);
    CycleRecord rec{};
    rec.idx = idx;
    rec.t_release_ns = t_rel;
    rec.t_wake_ns = mono_ns();
    uint16_t flags = 0;

    // ---------------------------------------------------------------- inputs
    int64_t t0 = mono_ns();
    Result rr = robot.getCurrentState(rs);
    const bool comm_error = rr == Result::CommError;
    if (rr == Result::Ok && rs.valid && rs.seq != last_state_seq) { last_state_seq = rs.seq; last_state_ns = rs.t_ns; }
    const bool have_hs = c.fusion && c.fusion->latest(hs);
    const int64_t t1 = mono_ns();
    const int64_t age_ns = have_hs && hs.available ? t1 - hs.t_obs_ns : INT64_MAX / 4;

    // ---------------------------------------------------------------- nominal controller
    double task_cycle_s = 0;
    if (c.tasks->update(rs, t1, task, &task_cycle_s) && c.ev)
      c.ev->emit(EventKind::Info, 0, task_cycle_s, c.tasks->completed(), "task_cycle");
    c.nominal->computeNominal(rs, task, qd_nom);
    const int mission = c.bus ? c.bus->mission.load() : 1;
    if (mission == static_cast<int>(MissionCmd::Pause)) for (int i = 0; i < qd_nom.n; ++i) qd_nom[i] = 0;
    const int64_t t2 = mono_ns();

    // ---------------------------------------------------------------- geometric barrier (always)
    c.geo->set_floor(c.sup->floor());
    c.geo->set_data_age(age_ns < INT64_MAX / 8 ? age_ns * 1e-9 : 0.0);
    c.geo->evaluate(rs, hs, gset);
    const int64_t t3 = mono_ns();

    // ---------------------------------------------------------------- supervisor
    SupervisorInputs in;
    in.now_ns = t3;
    in.robot_state_valid = rs.valid;
    in.robot_state_age_ns = last_state_ns ? t3 - last_state_ns : 0;
    in.robot_comm_error = comm_error;
    in.estimate_available = have_hs && hs.available;
    in.estimate_age_ns = age_ns;
    in.streams_alive = have_hs ? hs.streams_alive : 0;
    in.streams_total = c.streams_total;
    in.mean_conf = have_hs ? hs.mean_conf : 0;
    // Constraint violation is judged on the measured separation against the active floor, not on
    // the barrier value (which is deliberately tightened for data age and human motion).
    in.h_geo = c.geo->last_min_separation() > -1 ? c.geo->last_min_separation() - c.sup->floor() : 1e9;
    in.learned_failed = learned_failed_prev;
    in.qp_relaxed = qp_relaxed_prev;
    in.previous_cycle_overrun = prev_overrun;
    in.memory_fault = c.inj && c.inj->memory_fault.exchange(false);
    in.config_rejected = c.config_rejected.exchange(false);
    if (c.ack_request.exchange(false)) c.sup->acknowledge(t3);
    const Mode mode = c.sup->update(in);
    c.mode = static_cast<int>(mode);
    // 3.1: a floor raised by this update applies to this cycle's rows (3.0 applied it one cycle later)
    c.geo->retighten(gset, c.sup->floor());

    // ---------------------------------------------------------------- learned barrier
    bool learned_used = false;
    learned_failed_prev = false;
    rec.h_learned = NAN;
    int64_t t4 = t3;
    if (c.strategy == Strategy::Proposed && c.learned_enabled && c.learned && c.sup->learned_allowed()) {
      c.learned->evaluate(rs, hs, lset);
      t4 = mono_ns();
      const auto& lt = c.learned->timing();
      rec.h_learned = static_cast<float>(c.learned->last_h());
      rec.d_remote_compute_ns = static_cast<int32_t>(lt.remote_compute_ns);
      if (lt.remote) flags |= kFlagRemoteInference;
      if (lt.timeout) flags |= kFlagRemoteTimeout;
      const bool over_budget = (t4 - t3) > static_cast<int64_t>(c.learned_budget_ms * 1e6);
      learned_failed_prev = lt.timeout || over_budget || !std::isfinite(c.learned->last_h());
      learned_used = lset.trustworthy && lset.n > 0 && !learned_failed_prev;
      if (!lset.trustworthy) flags |= kFlagLearnedUntrusted;
    } else {
      lset.clear();
      if (c.strategy == Strategy::Proposed) flags |= kFlagLearnedUntrusted;
    }

    // ---------------------------------------------------------------- safety strategy
    // Release 3.1. Every limit that applies to the command is enforced INSIDE the QP, so the
    // dispatched command is the QP solution itself and satisfies every active barrier row:
    //   * supervisor speed scale s (composed over active conditions): box sigma*qd_max and
    //     nominal sigma*qd_nom with sigma = s;
    //   * SSM speed limit v_ok (ISO/TS 15066 5.5.4): if the solution's largest link-point speed
    //     exceeds v_ok, sigma is reduced and the QP RE-SOLVED (rows kept), never scaled afterwards;
    //   * if the rows cannot be met within the speed limits (they would require the robot to move
    //     away faster than allowed), the conflict is handled explicitly: protective stop,
    //     kFlagLimitConflict;
    //   * a final check of the command actually dispatched against all rows, the box and v_ok;
    //     any violation -> protective stop, kFlagFinalCheckFailed; the residual is logged.
    // Release 3.0 multiplied the QP solution by the mode scale and the SSM ratio after solving,
    // which can violate a row with rhs > 0 (Reviewer 2, round 4).
    qp_relaxed_prev = false;
    bool stop_cmd = c.sup->stopped() || mission == static_cast<int>(MissionCmd::Abort);
    QpResult qr{};
    const double s_mode = c.sup->speed_scale();
    const double sep = c.geo->last_min_separation();
    const double t_age = age_ns < INT64_MAX / 8 ? age_ns * 1e-9 : 0.0;
    const bool ssm_on = (c.ssm_monitor || c.strategy == Strategy::Ssm) && c.strategy != Strategy::PotentialField && sep > -1;
    const double v_ok = ssm_on ? max_speed_for_separation(c.ssm, sep, t_age) : -1.0;
    const double psd = ssm_on ? protective_separation(c.ssm, v_ok, t_age).total : 0.0;
    double sigma = s_mode;           // fraction of the nominal speed envelope actually used
    const ConstraintSet* rows[2] = {nullptr, nullptr};
    if (!stop_cmd) {
      switch (c.strategy) {
        case Strategy::Proposed:
        case Strategy::HcCbf: {
          rows[0] = &gset;
          rows[1] = learned_used ? &lset : nullptr;
          const LimitedFilterResult lf =
              limited_filter(qp, *c.geo, qd_nom, c.qd_max, s_mode, ssm_on ? v_ok : -1.0, rows[0], rows[1], qd_cmd);
          qr.iters = lf.iters;
          qr.feasible = !lf.stop;
          if (lf.relaxed) { flags |= kFlagQpRelaxed; qp_relaxed_prev = true; rows[1] = nullptr; }
          if (lf.ssm_reduced) flags |= kFlagSsmReduced;
          if (lf.qp_failed) flags |= kFlagQpFailed;
          if (lf.limit_conflict) flags |= kFlagLimitConflict;
          if (lf.stop) stop_cmd = true;
          sigma = lf.sigma;
          break;
        }
        case Strategy::Ssm: {
          // speed-and-separation baseline: no barrier rows, so scaling cannot violate any row
          qd_cmd = qd_nom;
          for (int j = 0; j < qd_cmd.n; ++j) qd_cmd[j] *= sigma;
          if (ssm_on) {
            const double v = c.geo->link_speed(qd_cmd);
            if (v > v_ok) {
              flags |= kFlagSsmReduced;
              const double r = v > 1e-9 ? v_ok / v : 0.0;
              for (int j = 0; j < qd_cmd.n; ++j) qd_cmd[j] *= r;
              sigma *= r;
            }
          }
          break;
        }
        case Strategy::PotentialField: {
          qd_cmd = qd_nom;
          for (int r = 0; r < gset.n; ++r) {
            const double d = gset.rows[static_cast<size_t>(r)].h + c.geo->floor();
            if (d >= c.pf.d0) continue;
            const double dd = std::max(d, 0.02);
            const double k = c.pf.k_rep * (1.0 / dd - 1.0 / c.pf.d0) / (dd * dd);
            for (int j = 0; j < qd_cmd.n; ++j) qd_cmd[j] += k * gset.rows[static_cast<size_t>(r)].a[static_cast<size_t>(j)];
          }
          for (int j = 0; j < qd_cmd.n; ++j) qd_cmd[j] = std::clamp(qd_cmd[j], -c.qd_max[j], c.qd_max[j]) * sigma;
          break;
        }
      }
    }
    // ---------------------------------------------------------------- final check of the dispatched command
    double final_viol = 0.0;
    if (!stop_cmd) {
      final_viol = command_violation(*c.geo, qd_cmd, c.qd_max, s_mode, ssm_on ? v_ok : -1.0, rows, 2);
      if (final_viol > 1e-6) { flags |= kFlagFinalCheckFailed; stop_cmd = true; }
    }
    const double scale = sigma;
    const int64_t t5 = mono_ns();

    // ---------------------------------------------------------------- injected overrun
    if (c.inj) {
      int ms = c.inj->overrun_ms.exchange(0);
      if (ms > 0) {
        flags |= kFlagInjectedOverrun;
        const int64_t until = mono_ns() + ms * 1000000LL;
        while (mono_ns() < until) {
        }
      }
    }

    // ---------------------------------------------------------------- dispatch
    const int64_t t6 = mono_ns();
    if (c.bus) {
      double ov = c.bus->override_.load();
      if (ov != last_override) { robot.setOverride(ov); last_override = ov; }
    }
    if (stop_cmd) {
      flags |= kFlagStopCommanded;
      robot.protectiveStop(c.stop_decel_joint);
    } else {
      robot.streamJointVelocity(qd_cmd, c.period_ns * 1e-9);
    }
    const int64_t t7 = mono_ns();

    // ---------------------------------------------------------------- record
    rec.d_state_ns = static_cast<int32_t>(t1 - t0);
    rec.d_nominal_ns = static_cast<int32_t>(t2 - t1);
    rec.d_geo_ns = static_cast<int32_t>(t3 - t2);
    rec.d_learned_ns = static_cast<int32_t>(t4 - t3);
    rec.d_qp_ns = static_cast<int32_t>(t5 - (t4 > t3 ? t4 : t3));
    rec.d_dispatch_ns = static_cast<int32_t>(t7 - t6);
    rec.h_geo = static_cast<float>(gset.n ? gset.h_min : NAN);
    rec.min_sep_m = static_cast<float>(sep);
    rec.human_age_ms = static_cast<float>(age_ns < INT64_MAX / 8 ? age_ns * 1e-6 : -1);
    rec.psd_m = static_cast<float>(psd);
    rec.speed_scale = static_cast<float>(stop_cmd ? 0 : scale);
    double nrm = 0;
    for (int j = 0; j < qd_cmd.n; ++j) nrm += qd_cmd[j] * qd_cmd[j];
    rec.qd_norm = static_cast<float>(stop_cmd ? 0 : std::sqrt(nrm));
    rec.mean_conf = static_cast<float>(have_hs ? hs.mean_conf : 0);
    rec.mode = static_cast<uint8_t>(mode);
    rec.qp_iters = static_cast<uint8_t>(std::min(255, qr.iters));
    rec.qp_rows = static_cast<uint8_t>(gset.n + (learned_used ? lset.n : 0));
    rec.streams_alive = static_cast<uint8_t>(have_hs ? hs.streams_alive : 0);
    for (int j = 0; j < kMaxDof; ++j) {
      rec.q[j] = j < rs.q.n ? static_cast<float>(rs.q[j]) : 0.0f;
      rec.qd_cmd[j] = (j < qd_cmd.n && !stop_cmd) ? static_cast<float>(qd_cmd[j]) : 0.0f;
    }
    {
      const Vec3 kp = c.geo->last_closest_keypoint();
      rec.closest_kp[0] = static_cast<float>(kp.x); rec.closest_kp[1] = static_cast<float>(kp.y); rec.closest_kp[2] = static_cast<float>(kp.z);
    }
    if (!(have_hs && hs.available)) flags |= kFlagEstimateUnavailable;
    // ---- 3.1 fields
    rec.final_viol = static_cast<float>(final_viol);
    rec.v_ssm_ok = static_cast<float>(ssm_on ? v_ok : -1.0);
    {
      double m2 = 0;
      for (int j = 0; j < rs.qd.n; ++j) m2 += rs.qd[j] * rs.qd[j];
      rec.qd_meas_norm = static_cast<float>(std::sqrt(m2));
    }
    rec.cond_mask = c.sup->active_mask();
    rec.d_enqueue_prev_ns = d_enqueue_prev;
    rec.gt_min_sep_m = NAN;
    rec.est_err_max_m = NAN;
    rec.est_err_closest_m = NAN;
    rec.gt_age_ms = NAN;
    if (c.gt) {
      GtSample g;
      if (c.gt->load(g)) {
        rec.gt_min_sep_m = static_cast<float>(g.sep);
        rec.gt_age_ms = static_cast<float>((t7 - g.t_gt_ns) * 1e-6);
        if (have_hs && hs.available)
          for (int k = 0; k < GtSample::kRing; ++k)
            if (g.t_obs[k] == hs.t_obs_ns) {
              rec.est_err_max_m = static_cast<float>(g.err[k]);
              rec.est_err_closest_m = static_cast<float>(g.err_closest[k]);
            }
      }
    }
    {
      const bool ctrl_stop = (flags & (kFlagQpFailed | kFlagLimitConflict | kFlagFinalCheckFailed)) != 0;
      if (ctrl_stop != ctrl_stop_prev && c.ev)
        c.ev->emit(EventKind::Info, 0, 0, flags, ctrl_stop ? "controller_stop_begin" : "controller_stop_end");
      ctrl_stop_prev = ctrl_stop;
    }
    if (c.bus) {
      Telemetry tm;
      tm.t_ns = t7; tm.q = rs.q; tm.qd = rs.qd; tm.min_sep_m = sep; tm.h_geo = gset.h_min;
      tm.mode = static_cast<uint8_t>(mode); tm.learned_active = learned_used; tm.estimate_available = in.estimate_available;
      tm.cycle = idx; tm.task_cycles = c.tasks->completed();
      c.bus->telemetry.store(tm);
    }
    // ---------------------------------------------------------------- end of cycle (3.1)
    // Execution time = wake-up -> completion of the enqueue of this record. t_end_ns is taken when
    // the record is complete; the enqueue that follows is measured and written into the NEXT
    // record (d_enqueue_prev_ns), so exec = t_end_ns - t_wake_ns + next.d_enqueue_prev_ns exactly.
    // The deadline seen by the supervisor and counted in the summary is judged at enqueue completion.
    const int64_t deadline = t_rel + c.period_ns;
    const int64_t t_end = mono_ns();
    rec.t_end_ns = t_end;
    rec.d_log_ns = static_cast<int32_t>(t_end - t7);
    if (t_end > deadline) flags |= kFlagOverrun;
    if (flags & kFlagInjectedOverrun) ++c.injected_overrun_cycles;

    // next release; releases that are already in the past are skipped, never bunched
    t_rel += c.period_ns;
    const int64_t now = mono_ns();
    if (now > t_rel) {
      flags |= kFlagReleaseLate;
      ++c.late_releases;
      while (t_rel < now) t_rel += c.period_ns;
    }
    rec.flags = flags;
    c.log->push_cycle(rec);
    const int64_t t_q = mono_ns();
    d_enqueue_prev = static_cast<int32_t>(t_q - t_end);
    const bool overrun = t_q > deadline;
    if (overrun) ++c.deadline_misses;
    prev_overrun = overrun;
    c.heartbeat_ns = t_q;
    if (t_q > t_rel) {  // the enqueue itself made the next release late: skip it (visible as a gap in t_release_ns)
      ++c.late_releases;
      while (t_rel < t_q) t_rel += c.period_ns;
    }
    ++c.cycles;
  }
  c.running = false;
  robot.protectiveStop(c.stop_decel_joint);
}

void background_load(std::atomic<bool>& run, double duty, int cpu) {
  if (cpu >= 0) {
    cpu_set_t s;
    CPU_ZERO(&s);
    CPU_SET(cpu, &s);
    pthread_setaffinity_np(pthread_self(), sizeof s, &s);
  }
  volatile double x = 1.0;
  while (run) {
    const int64_t t0 = mono_ns();
    while (mono_ns() - t0 < static_cast<int64_t>(10e6 * duty)) x = x * 1.0000001 + 1e-9;
    std::this_thread::sleep_for(std::chrono::nanoseconds(static_cast<int64_t>(10e6 * (1 - duty))));
  }
}

}  // namespace

int main(int argc, char** argv) {
  std::string cfg_path, variant, run_root = "runs", notes;
  bool run_root_cli = false;
  std::vector<std::string> backups;
  double duration_override = -1;
  long long seed_override = -1;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto next = [&]() -> std::string { if (i + 1 >= argc) { std::fprintf(stderr, "%s", usage().c_str()); std::exit(2); } return argv[++i]; };
    if (a == "--config") cfg_path = next();
    else if (a == "--variant") variant = next();
    else if (a == "--duration") duration_override = std::stod(next());
    else if (a == "--seed") seed_override = std::stoll(next());
    else if (a == "--backup") backups.push_back(next());
    else if (a == "--run-root") { run_root = next(); run_root_cli = true; }
    else if (a == "--notes") notes = next();
    else { std::fprintf(stderr, "%s", usage().c_str()); return 2; }
  }
  if (cfg_path.empty()) { std::fprintf(stderr, "%s", usage().c_str()); return 2; }
  signal(SIGINT, on_signal);
  signal(SIGTERM, on_signal);

  Json cfg = Json::parse_file(cfg_path);
  const double duration_s = duration_override > 0 ? duration_override : cfg["duration_s"].num(60);
  const uint64_t seed = seed_override >= 0 ? static_cast<uint64_t>(seed_override) : static_cast<uint64_t>(cfg["seed"].i64(1));
  for (size_t i = 0; i < cfg["logging"]["backup_dirs"].size(); ++i) backups.push_back(cfg["logging"]["backup_dirs"][i].str());
  if (!run_root_cli && cfg["logging"].has("run_root")) run_root = cfg.get("logging.run_root", run_root);

  // ------------------------------------------------------------------ logger
  RunLogger logger;
  RunInfo info;
  info.run_root = run_root;
  info.experiment = cfg["experiment"].str_or("run");
  info.variant = variant.empty() ? cfg["variant"].str_or("") : variant;
  info.config_path = cfg_path;
  info.backup_dirs = backups;
  info.notes = notes;
  const std::string dir = logger.open(info);
  std::fprintf(stderr, "[hrc_run] run directory: %s\n", dir.c_str());
  if (backups.empty())
    std::fprintf(stderr, "[hrc_run] WARNING: no backup directory configured; this run will exist in one place only.\n");
  EventChannel* ev_ctrl = logger.channel("control");
  EventChannel* ev_sup = logger.channel("supervisor");
  EventChannel* ev_inj = logger.channel("injector");
  EventChannel* ev_wd = logger.channel("watchdog");
  EventChannel* ev_op = logger.channel("operator");
  EventChannel* ev_main = logger.channel("main");
  {
    JsonWriter w;
    w.begin_object().kv("duration_s", duration_s).kv("seed", static_cast<int64_t>(seed)).end_object();
    logger.annotate("run_parameters", w.str());
  }

  // ------------------------------------------------------------------ robot
  DhParams dh = cfg["robot"].has("dh") ? DhParams::from_json_file(cfg.get("robot.dh", std::string())) : DhParams::ur5e();
  const std::string backend = cfg.get("robot.backend", std::string("sim"));
  std::unique_ptr<IRobotController> robot_owned;
  SimRobot* sim_robot = nullptr;
  Limits limits;
  for (auto* j : {&limits.qmin, &limits.qmax, &limits.qd_max, &limits.qdd_max}) j->n = dh.n;
  for (int i = 0; i < dh.n; ++i) {
    limits.qmin[i] = -2 * M_PI; limits.qmax[i] = 2 * M_PI;
    limits.qd_max[i] = cfg["robot"]["qd_max"][size_t(i)].num(1.0);
    limits.qdd_max[i] = cfg["robot"]["qdd_max"][size_t(i)].num(4.0);
  }
  Joints q0 = joints_from(cfg["task"]["waypoints"][size_t(0)], dh.n);
  if (backend == "sim") {
    SimRobotParams sp;
    sp.dh = dh;
    sp.rate_hz = cfg.get("robot.rate_hz", 500.0);
    sp.tau_s = cfg.get("robot.tau_s", 0.02);
    sp.cmd_latency_ms = cfg.get("robot.cmd_latency_ms", 2.0);
    sp.state_latency_ms = cfg.get("robot.state_latency_ms", 2.0);
    sp.limits = limits;
    sp.q0 = q0;
    auto r = std::make_unique<SimRobot>(sp);
    sim_robot = r.get();
    robot_owned = std::move(r);
  } else if (backend == "ur_rtde") {
    robot_owned = std::make_unique<UrRtdeAdapter>();
  } else if (backend == "kuka_fri") {
    robot_owned = make_kuka_fri_adapter();
  } else if (backend == "abb_egm") {
    robot_owned = make_abb_egm_adapter();
  }
  if (!robot_owned) {
    std::fprintf(stderr, "[hrc_run] backend '%s' not available in this build\n", backend.c_str());
    logger.close("failed_setup");
    return 3;
  }
  ConnectionConfig cc;
  cc.host = cfg.get("robot.host", std::string("127.0.0.1"));
  cc.port = static_cast<int>(cfg.get("robot.port", 0.0));
  cc.timeout_ms = static_cast<int>(cfg.get("robot.timeout_ms", 2000.0));
  cc.options = cfg["robot"]["options"].dump();
  if (robot_owned->connect(cc) != Result::Ok) {
    std::fprintf(stderr, "[hrc_run] cannot connect robot backend '%s' at %s:%d\n", backend.c_str(), cc.host.c_str(), cc.port);
    logger.close("failed_setup");
    return 3;
  }
  // transport variant (ablation A1)
  const std::string transport = cfg.get("rt.transport", std::string("shm"));
  const int ctrl_cpu = static_cast<int>(cfg.get("rt.cpu", -1.0));
  const bool shared_core = cfg.get_bool("rt.shared_core", false);
  const int aux_cpu = shared_core ? ctrl_cpu : static_cast<int>(cfg.get("rt.aux_cpu", -1.0));
  std::unique_ptr<SocketTransportRobot> sock_robot;
  IRobotController* robot = robot_owned.get();
  if (transport == "socket") { sock_robot = std::make_unique<SocketTransportRobot>(*robot_owned, aux_cpu); robot = sock_robot.get(); }

  // ------------------------------------------------------------------ human, cameras, fusion
  HumanScriptParams hp;
  hp.scenario = cfg.get("human.scenario", std::string("pick_and_place"));
  hp.cycle_s = cfg.get("human.cycle_s", 18.0);
  hp.shared_zone_x = cfg.get("human.shared_zone_x", 0.55);
  hp.seed = seed ^ 0x1111;
  SimHuman human(hp);
  const int64_t t_sim0 = mono_ns();
  CameraParams cp;
  cp.n = static_cast<int>(cfg.get("sensors.cameras", 6.0));
  cp.fps = cfg.get("sensors.fps", 30.0);
  cp.latency_ms = cfg.get("sensors.latency_ms", 30.0);
  cp.occlusion_prob = cfg.get("sensors.occlusion_prob", 0.15);
  cp.seed = seed ^ 0x2222;
  SimCameraArray cams(cp, human, t_sim0);
  FusionParams fp;
  fp.rate_hz = cfg.get("sensors.fusion_hz", 50.0);
  fp.stream_timeout_ms = cfg.get("supervisor.stream_timeout_ms", 100.0);
  fp.cpu = aux_cpu;
  CameraFusion fusion(fp, cams);
  fusion.start();

  // ------------------------------------------------------------------ safety, control
  GeometricCbfParams gp;
  gp.kappa = cfg.get("control.kappa", 2.0);
  gp.max_rows = static_cast<int>(cfg.get("control.geo_rows", 6.0));
  gp.position_margin = cfg.get("control.position_margin", 0.0);  // 3.1; 0 = release 3.0 behaviour
  {
    const std::string mm = cfg.get("control.motion.model", std::string("bound"));
    gp.motion.worst_case = mm == "worst_case";
    gp.motion.measured = mm == "measured";
  }
  gp.motion.v_bound = cfg.get("control.motion.v_bound", 1.0);
  gp.motion.v_max = cfg.get("control.motion.v_max", 2.0);
  gp.motion.v_margin = cfg.get("control.motion.v_margin", 0.3);
  GeometricCbf geo(dh, gp);
  std::unique_ptr<LearnedCbf> learned;
  const bool learned_enabled = cfg.get_bool("control.learned.enabled", true);
  if (learned_enabled) {
    LearnedCbfParams lp;
    lp.weights_path = cfg.get("control.learned.weights", std::string("models/cbf_ur5e.json"));
    lp.kappa = gp.kappa;
    lp.gray_band = cfg.get("control.learned.gray_band", 0.15);
    lp.motion = gp.motion;
    lp.remote = cfg.get_bool("control.learned.remote", false);
    lp.remote_host = cfg.get("control.learned.host", std::string("127.0.0.1"));
    lp.remote_port = static_cast<int>(cfg.get("control.learned.port", 47011.0));
    lp.remote_timeout_us = static_cast<int>(cfg.get("control.learned.timeout_us", 5000.0));
    learned = std::make_unique<LearnedCbf>(dh, lp);
    if (!learned->ok()) {
      std::fprintf(stderr, "[hrc_run] learned barrier unavailable: %s\n", learned->error().c_str());
      ev_main->emit(EventKind::Warning, 0, 0, 0, "learned_unavailable");
      logger.annotate("learned_barrier", "{\"loaded\":false,\"error\":\"" + JsonWriter::escape(learned->error()) + "\"}");
      learned.reset();
    } else {
      logger.annotate("learned_barrier", "{\"loaded\":true,\"weights\":\"" + JsonWriter::escape(lp.weights_path) +
                                             "\",\"weights_sha256\":\"" + learned->model().sha256() + "\",\"remote\":" +
                                             (lp.remote ? "true" : "false") + "}");
    }
  }
  SupervisorParams spar;
  spar.estimate_hold_ms = cfg.get("supervisor.estimate_hold_ms", spar.estimate_hold_ms);
  spar.stream_timeout_ms = fp.stream_timeout_ms;
  spar.partition_timeout_ms = cfg.get("supervisor.partition_timeout_ms", spar.partition_timeout_ms);
  spar.violation_threshold = cfg.get("supervisor.violation_threshold", spar.violation_threshold);
  spar.conf_stop = cfg.get("supervisor.conf_stop", spar.conf_stop);
  spar.conf_low = cfg.get("supervisor.conf_low", spar.conf_low);
  Supervisor sup(spar, ev_sup);
  std::vector<Joints> wps;
  for (size_t i = 0; i < cfg["task"]["waypoints"].size(); ++i) wps.push_back(joints_from(cfg["task"]["waypoints"][i], dh.n));
  TaskSequencer tasks(wps, cfg.get("task.tolerance_rad", 0.02), cfg.get("task.dwell_s", 0.5));
  JointPController nominal(limits.qd_max);

  // ------------------------------------------------------------------ integration layer
  IntegrationBus bus;
  std::unique_ptr<ModbusServer> modbus;
  std::unique_ptr<RestServer> rest;
  std::unique_ptr<OpcUaServer> opcua;
  if (cfg.get_bool("integration.modbus.enabled", false)) {
    modbus = std::make_unique<ModbusServer>(bus, static_cast<int>(cfg.get("integration.modbus.port", 5020.0)), logger.channel("modbus"), aux_cpu);
    if (!modbus->start()) ev_main->emit(EventKind::Warning, 0, 0, 0, "modbus_start_failed");
  }
  if (cfg.get_bool("integration.rest.enabled", false)) {
    rest = std::make_unique<RestServer>(bus, static_cast<int>(cfg.get("integration.rest.port", 8080.0)), logger.channel("rest"), aux_cpu);
    if (!rest->start()) ev_main->emit(EventKind::Warning, 0, 0, 0, "rest_start_failed");
  }
  if (cfg.get_bool("integration.opcua.enabled", false)) {
    opcua = std::make_unique<OpcUaServer>(bus, static_cast<int>(cfg.get("integration.opcua.port", 4840.0)), logger.channel("opcua"), aux_cpu);
    if (!opcua->start()) ev_main->emit(EventKind::Warning, 0, 0, 0, "opcua_unavailable_in_build");
  }

  // ------------------------------------------------------------------ loop context
  LoopContext c;
  c.period_ns = static_cast<int64_t>(cfg.get("control.period_ms", 20.0) * 1e6);
  c.duration_ns = static_cast<int64_t>(duration_s * 1e9);
  c.strategy = strategy_from_string(cfg.get("control.strategy", std::string("proposed")));
  c.learned_enabled = learned != nullptr;
  c.learned_budget_ms = cfg.get("control.learned.budget_ms", 5.0);
  c.stop_decel_joint = cfg.get("control.stop_decel_joint", 3.0);
  c.ssm_monitor = cfg.get_bool("ssm.enabled", true);
  c.ssm.v_h = cfg.get("ssm.v_h", c.ssm.v_h);
  c.ssm.T_r = cfg.get("ssm.T_r", c.ssm.T_r);
  c.ssm.a_stop = cfg.get("ssm.a_stop", c.ssm.a_stop);
  c.ssm.C = cfg.get("ssm.C", c.ssm.C);
  c.ssm.Z_d = cfg.get("ssm.Z_d", c.ssm.Z_d);
  c.ssm.Z_r = cfg.get("ssm.Z_r", c.ssm.Z_r);
  c.pf.d0 = cfg.get("pf.d0", c.pf.d0);
  c.pf.k_rep = cfg.get("pf.k_rep", c.pf.k_rep);
  c.qd_max = limits.qd_max;
  c.fusion = &fusion;
  c.geo = &geo;
  c.learned = learned.get();
  c.sup = &sup;
  c.tasks = &tasks;
  c.nominal = &nominal;
  c.log = &logger;
  c.ev = ev_ctrl;
  c.bus = &bus;
  c.streams_total = cp.n;

  // ------------------------------------------------------------------ ground-truth probe (3.1, evaluation only)
  // Separation between the simulator's true robot state and the scripted human, and the error of
  // each fused estimate against the scripted keypoints at its observation time. Runs on the
  // auxiliary core at 250 Hz so that it adds nothing to the control path; never used for control.
  SeqlockSlot<GtSample> gt_slot;
  std::atomic<bool> gt_run{true};
  std::thread gt_thread;
  if (sim_robot && cfg.get_bool("logging.ground_truth", true)) {
    c.gt = &gt_slot;
    const double min_conf = gp.min_keypoint_conf;
    gt_thread = std::thread([&, dh, min_conf] {
      if (aux_cpu >= 0) {
        cpu_set_t s;
        CPU_ZERO(&s);
        CPU_SET(aux_cpu, &s);
        pthread_setaffinity_np(pthread_self(), sizeof s, &s);
      }
      Kinematics kin(dh);
      const double r_link = kin.params().link_radius;
      GtSample g;
      std::array<Vec3, kKeypoints> kp;
      RobotState ts;
      HumanState est;
      int64_t last_obs = 0;
      int64_t t = mono_ns();
      while (gt_run) {
        t += 4'000'000;
        sleep_until_mono(t);
        const int64_t now = mono_ns();
        if (sim_robot->true_state(ts)) {
          kin.update(ts.q);
          human.keypoints((now - t_sim0) * 1e-9, kp);
          double best = 1e9;
          for (const auto& lp : kin.points())
            for (const auto& p : kp) best = std::min(best, (lp.p - p).norm() - r_link);
          g.sep = best;
          g.t_gt_ns = now;
        }
        if (fusion.latest(est) && est.available && est.t_obs_ns != last_obs) {
          last_obs = est.t_obs_ns;
          human.keypoints((est.t_obs_ns - t_sim0) * 1e-9, kp);
          double e = 0, e_closest = NAN, d_closest = 1e9;
          for (int j = 0; j < kKeypoints; ++j) {
            if (est.conf[static_cast<size_t>(j)] < min_conf) continue;
            const double ej = (est.kp[static_cast<size_t>(j)] - kp[static_cast<size_t>(j)]).norm();
            e = std::max(e, ej);
            double dj = 1e9;  // distance of the ESTIMATED keypoint to the robot (true state, last probe)
            for (const auto& lp : kin.points()) dj = std::min(dj, (lp.p - est.kp[static_cast<size_t>(j)]).norm());
            if (dj < d_closest) { d_closest = dj; e_closest = ej; }
          }
          g.t_obs[g.head] = est.t_obs_ns;
          g.err[g.head] = e;
          g.err_closest[g.head] = e_closest;
          g.head = (g.head + 1) % GtSample::kRing;
        }
        gt_slot.store(g);
      }
    });
  }

  // ------------------------------------------------------------------ fault campaign
  InjectionTargets tg;
  tg.stream_timeout = [&](int cam, double s) { cams.inject_stream_timeout(cam, s); };
  tg.confidence_drop = [&](double s) { cams.inject_confidence_drop(s, 0.3); };
  tg.partition = [&](double s) { if (sim_robot) sim_robot->inject_partition(s); };
  tg.comm_faults = [&](int n) { if (sim_robot) sim_robot->inject_comm_faults(n); };
  tg.lunge = [&](double s) {
    // right hand toward the current TCP at 2.0 m/s (above the 1.6 m/s scripted bound).
    // 3.1: the TCP comes from the simulator's state with a private kinematics object; 3.0 read
    // the control thread's kinematics from the injector thread (an unsynchronised access).
    Vec3 target{};
    RobotState ts;
    if (sim_robot && sim_robot->true_state(ts)) {
      Kinematics k(dh);
      k.update(ts.q);
      target = k.tcp();
    }
    human.inject_lunge((mono_ns() - t_sim0) * 1e-9, s, target, 2.0);
  };
  tg.bad_config = [&]() { c.config_rejected = true; };  // validator rejects a negative separation floor
  c.inj = &tg;
  FaultCampaignParams fcp;
  fcp.enabled = cfg.get_bool("faults.enabled", false);
  fcp.arrival = cfg.get("faults.arrival", std::string("poisson"));
  fcp.mean_cluster_size = cfg.get("faults.mean_cluster_size", 3.0);
  fcp.cluster_spread_s = cfg.get("faults.cluster_spread_s", 30.0);
  fcp.weibull_shape = cfg.get("faults.weibull_shape", 1.0);
  fcp.rate_scale = cfg.get("faults.rate_scale", 1.0);
  fcp.rate_sensor_timeout = cfg.get("faults.rates_per_h.sensor_timeout", 0.0);
  fcp.rate_tracking_loss = cfg.get("faults.rates_per_h.tracking_loss", 0.0);
  fcp.rate_network_partition = cfg.get("faults.rates_per_h.network_partition", 0.0);
  fcp.rate_overrun = cfg.get("faults.rates_per_h.computational_overrun", 0.0);
  fcp.rate_hw_comm = cfg.get("faults.rates_per_h.hardware_communication", 0.0);
  fcp.rate_memory = cfg.get("faults.rates_per_h.memory_allocation", 0.0);
  fcp.rate_config = cfg.get("faults.rates_per_h.configuration_inconsistency", 0.0);
  fcp.rate_constraint = cfg.get("faults.rates_per_h.constraint_violation", 0.0);
  fcp.seed = seed ^ 0x3333;
  auto schedule = make_schedule(fcp, duration_s);
  write_schedule_csv(schedule, (fs::path(dir) / "injection_schedule.csv").string());  // fixed before the first cycle

  // ------------------------------------------------------------------ simulated operator
  const double op_median_s = cfg.get("operator.ack_median_s", 60.0);
  const double op_sigma = cfg.get("operator.ack_log_sigma", 0.5);
  std::atomic<bool> aux_run{true};
  std::thread op_thread([&] {
    std::mt19937_64 rng(seed ^ 0x4444);
    std::lognormal_distribution<double> d(std::log(op_median_s), op_sigma);
    while (aux_run) {
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
      const int m = c.mode.load();
      if (m == static_cast<int>(Mode::ProtectiveStopLatched) || m == static_cast<int>(Mode::EmergencyStop)) {
        const double wait = d(rng);
        ev_op->emit(EventKind::Info, 0, wait, m, "simulated_operator_dispatched");
        const int64_t until = mono_ns() + static_cast<int64_t>(wait * 1e9);
        while (aux_run && mono_ns() < until) std::this_thread::sleep_for(std::chrono::milliseconds(20));
        if (!aux_run) break;
        if (sim_robot) sim_robot->resetFault();
        c.ack_request = true;
        ev_op->emit(EventKind::OperatorAck, 0, wait, m, "simulated_operator_ack");
        while (aux_run && c.mode.load() >= static_cast<int>(Mode::ProtectiveStopLatched)) std::this_thread::sleep_for(std::chrono::milliseconds(20));
      }
    }
  });

  // ------------------------------------------------------------------ background load
  std::vector<std::thread> load_threads;
  const int n_load = static_cast<int>(cfg.get("background_load.threads", 0.0));
  const double duty = cfg.get("background_load.duty", 0.4);
  for (int i = 0; i < n_load; ++i) load_threads.emplace_back(background_load, std::ref(aux_run), duty, shared_core ? ctrl_cpu : -1);

  // ------------------------------------------------------------------ wait for inputs
  {
    RobotState rs;
    HumanState hs;
    const int64_t until = mono_ns() + 5'000'000'000LL;
    while (mono_ns() < until && !(robot->getCurrentState(rs) == Result::Ok && rs.valid && fusion.latest(hs) && hs.available))
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  // ------------------------------------------------------------------ watchdog
  const bool wd_enabled = cfg.get_bool("watchdog.enabled", true);
  const int64_t wd_limit = c.period_ns + static_cast<int64_t>(cfg.get("watchdog.grace_ms", 40.0) * 1e6);
  std::thread wd_thread;
  if (wd_enabled) {
    wd_thread = std::thread([&] {
      RtSettings ws;
      ws.policy = cfg.get("rt.policy", std::string("fifo"));
      ws.priority = static_cast<int>(cfg.get("rt.priority", 90.0)) + 1;
      ws.cpu = aux_cpu;
      ws.lock_memory = false;
      apply_rt(ws);
      bool tripped = false;
      while (aux_run) {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
        if (!c.running) continue;
        const int64_t gap = mono_ns() - c.heartbeat_ns.load();
        if (!tripped && gap > wd_limit) {
          robot_owned->protectiveStop(c.stop_decel_joint);  // direct path, bypasses any transport
          sup.watchdog_trip(mono_ns());
          ev_wd->emit(EventKind::FaultDetected, static_cast<uint8_t>(FaultCategory::ComputationalOverrun), gap * 1e-6, 0, "watchdog_stop");
          tripped = true;
        } else if (tripped && gap < c.period_ns) {
          tripped = false;
        }
      }
    });
  }

  // ------------------------------------------------------------------ run
  RtSettings rt;
  rt.policy = cfg.get("rt.policy", std::string("fifo"));
  rt.priority = static_cast<int>(cfg.get("rt.priority", 90.0));
  rt.cpu = ctrl_cpu;
  rt.lock_memory = cfg.get_bool("rt.lock_memory", true);
  RtApplied applied = apply_rt(rt);
  logger.annotate("rt_applied", applied.to_json());
  if (!applied.policy_ok)
    std::fprintf(stderr, "[hrc_run] WARNING: real-time policy not applied (%s). The run is recorded as non-RT.\n", applied.error.c_str());

  FaultInjector injector(schedule, tg, ev_inj, mono_ns());
  injector.start();
  const std::string arch = cfg.get("architecture", std::string("layered"));
  if (arch == "monolithic" && sim_robot && transport == "shm") {
    control_loop<SimRobot>(c, *sim_robot);  // A0: static dispatch, no interface indirection
  } else {
    control_loop<IRobotController>(c, *robot);
  }

  // ------------------------------------------------------------------ shutdown and provenance
  injector.stop();
  aux_run = false;
  gt_run = false;
  if (gt_thread.joinable()) gt_thread.join();
  if (wd_thread.joinable()) wd_thread.join();
  op_thread.join();
  for (auto& t : load_threads) t.join();
  if (modbus) modbus->stop();
  if (rest) rest->stop();
  if (opcua) opcua->stop();
  fusion.stop();
  {
    FusionStats fs_ = fusion.stats();
    std::string h = "{\"bin_us\":10,\"publishes\":" + std::to_string(fs_.publishes) + ",\"counts_sparse\":{";
    bool first = true;
    for (int i = 0; i <= FusionStats::kBins; ++i) {
      if (!fs_.exec_hist[static_cast<size_t>(i)]) continue;
      h += (first ? "" : ",") + std::string("\"") + std::to_string(i) + "\":" + std::to_string(fs_.exec_hist[static_cast<size_t>(i)]);
      first = false;
    }
    logger.annotate("fusion_exec_hist", h + "}}");
  }
  if (auto* ur = dynamic_cast<UrRtdeAdapter*>(robot_owned.get())) {
    auto& hs = ur->handshake();
    logger.annotate("ur_rtde", "{\"controller_version\":\"" + std::to_string(hs.major) + "." + std::to_string(hs.minor) + "." +
                                   std::to_string(hs.bugfix) + "." + std::to_string(hs.build) + "\",\"stats\":" + ur->stats().to_json() + "}");
  }
  {
    JsonWriter w;
    w.begin_object()
        .kv("architecture", arch).kv("transport", transport).kv("strategy", to_string(c.strategy))
        .kv("backend", backend).kv("robot_model", dh.model)
        .kv("cycles", static_cast<int64_t>(c.cycles)).kv("deadline_misses_total", static_cast<int64_t>(c.deadline_misses))
        .kv("injected_overrun_cycles", static_cast<int64_t>(c.injected_overrun_cycles))
        .kv("late_releases", static_cast<int64_t>(c.late_releases)).kv("task_cycles", static_cast<int64_t>(tasks.completed()))
        .kv("injections_scheduled", static_cast<int64_t>(schedule.size())).kv("interrupted_by_signal", g_stop.load())
        .end_object();
    logger.annotate("summary", w.str());
  }
  robot_owned->disconnect();
  const bool backups_ok = logger.close(g_stop ? "interrupted" : "complete");
  std::fprintf(stderr, "[hrc_run] %llu cycles, %llu deadline misses (%llu with injected overrun). Backups %s.\n",
               static_cast<unsigned long long>(c.cycles), static_cast<unsigned long long>(c.deadline_misses),
               static_cast<unsigned long long>(c.injected_overrun_cycles), backups_ok ? "verified" : "NOT verified");
  return backups_ok || backups.empty() ? 0 : 4;
}
