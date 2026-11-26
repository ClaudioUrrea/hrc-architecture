# Runbook: producing the data for the paper

Every step below produces raw files written by software; none produces numbers by hand.
Times are wall-clock estimates for the default campaign sizes.

## As executed for the article

This runbook is the procedure written before the campaigns. The campaigns of the article
followed it with these differences, which the article reports in its Section 5.8:

* **Host.** One workstation (Intel Core i7-12700, 32 GB) running Ubuntu 22.04 under WSL2 with
  the general-purpose `PREEMPT_DYNAMIC` kernel. No PREEMPT_RT kernel, no isolated CPUs, and
  `sched_rt_runtime_us` at its default (section 1 was not applied). `SCHED_FIFO` priority 90,
  CPU affinity and locked memory were requested and obtained in every run.
* **Robot.** Every campaign used the built-in kinematic UR5e model. URSim was used only for
  the conformance test (section 6); the URSim timing variant was not run.
* **Not executed:** KUKA and ABB conformance, the remote-inference variant, PLC commissioning
  timing and porting-effort logs (section 9). No result is reported for them.
* **Sizes.** Full design sizes: timing 120 blocks of 100 min, tuning segments of 20 min,
  comparison 120 runs of 20 min.

The frozen configurations are at tag `campaign-v3`, the comparison configurations at
`campaign-v3-compare`, and the code that generated `results.json` at `campaign-v3-report`.

## 0. Machines

| Role | Requirement | Used for |
|---|---|---|
| Control host | x86-64, ≥ 8 cores, Ubuntu 22.04 with a PREEMPT_RT kernel | `hrc_run`, all campaigns |
| Inference device (optional) | any Linux device on a dedicated Ethernet link (e.g. Jetson) | `hrc_infer_server`, remote-inference variant |
| URSim | Docker on the control host or a second PC | UR adapter conformance and URSim runs |
| Windows PC | TIA Portal + PLCSIM Advanced, Studio 5000 + Logix Emulate, GX Works3 | PLC commissioning timing |

## 1. Real-time host (once, ~2 h)

```bash
sudo apt install linux-image-rt-amd64 || true   # or build a PREEMPT_RT kernel for 22.04
# kernel command line (GRUB_CMDLINE_LINUX_DEFAULT): isolcpus=4-7 nohz_full=6,7 rcu_nocbs=6,7
sudo update-grub && sudo reboot
cat /sys/kernel/realtime            # must print 1
echo -1 | sudo tee /proc/sys/kernel/sched_rt_runtime_us
sudo cpupower frequency-set -g performance
# allow SCHED_FIFO and mlock for your user
echo "$USER - rtprio 95" | sudo tee -a /etc/security/limits.d/rt.conf
echo "$USER - memlock unlimited" | sudo tee -a /etc/security/limits.d/rt.conf
```

Every run manifest records the kernel, `isolated_cpus`, the governor and whether SCHED_FIFO
was actually applied. Runs where it was not are excluded from timing results automatically.

## 2. Build and test (~10 min)

```bash
sudo apt install build-essential cmake git python3-numpy python3-scipy cloc
pip install lizard
git clone https://github.com/ClaudioUrrea/hrc-architecture && cd hrc-architecture
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
cd build && ctest --output-on-failure && cd ..
```
Optional components: `-DHRC_FRI_SDK_DIR=...` (KUKA FRI client SDK), `-DHRC_EGM_PROTO=.../egm.proto`
(ABB EGM; needs protobuf), open62541 (OPC-UA; detected automatically).

**Commit everything before any run.** A manifest whose `git_commit` ends in `-dirty` is not
acceptable for the paper.

## 3. Backups (once)

Mount an external disk and a cloud-synced folder, e.g. `/media/$USER/HRC_BACKUP/runs` and
`~/OneDrive/hrc_runs`. Every campaign command below passes both with `--backup`. The runner
refuses to start without one.

## 4. Pilot and freeze (~1 day)

```bash
python3 train/train_cbf.py --n-train 8000 --n-test 2000 --epochs 20 --run-root runs_pilot
cp runs_pilot/*_cbf_train/model.json models/cbf_ur5e.json      # pilot model only
./build/hrc_run --config cfg/base_sim_ur5e.json --duration 300 --run-root runs_pilot --notes pilot
python3 -c "import sys; sys.path.insert(0,'analysis'); import hrc_logs as H; ..."   # inspect
```
Use the pilot to fix scenario geometry, task waypoints and controller gains so that the cell
works. Then **freeze**: commit `cfg/base_sim_ur5e.json`, run
`python3 tools/make_campaigns.py all`, commit `cfg/campaigns/`, and `git tag campaign-v3`.
Pilot runs never enter the paper.

## 5. Barrier network (~1 h)

```bash
python3 train/train_cbf.py --robot cfg/robots/ur5e.json --n-train 40000 --n-test 10000 \
    --n-gray 5000 --epochs 200 --seed 20261012 --run-root runs --backup /media/.../runs
cp runs/*_cbf_train/model.json models/cbf_ur5e.json && git add models && git commit -m "frozen barrier model"
```
`metrics.json` in that run directory holds the held-out results the paper reports.

## 6. Interface conformance with URSim (~1 h)

```bash
docker run --rm -it -p 5900:5900 -p 6080:6080 -p 29999:29999 -p 30001-30004:30001-30004 \
    universalrobots/ursim_e-series        # note the URSim version shown on start-up
./build/hrc_conformance --backend ur_rtde --host 127.0.0.1 --backup /media/.../runs
```
The same for KUKA (Sunrise.OS + FRI) and ABB (RobotStudio virtual controller) only if those
adapters are built and their simulators are available; otherwise the paper reports them as not
evaluated.

## 7. Campaigns (run in this order)

| Campaign | Command | Run time |
|---|---|---|
| Ablation | `python3 tools/run_campaign.py cfg/campaigns/ablation --backup A --backup B` | 11.7 h |
| Fault injection | `... cfg/campaigns/injection ...` | 10 h |
| Baseline tuning | `... cfg/campaigns/tuning ...` | 66.7 h (or `--segment-minutes 10`: 33 h) |
| Select tuned parameters | `python3 analysis/report.py --runs runs` → `results/tuning_selection.json` | – |
| Comparison | `python3 tools/make_campaigns.py compare --selection results/tuning_selection.json`, commit, then run | 40 h |
| Fault sensitivity | `... cfg/campaigns/sensitivity ...` | 24 h |
| Timing (200 h) | `... cfg/campaigns/timing ...` | 200 h |

The runner is resumable: interrupt it at any time and start it again. A reduced plan that is
still meaningful (about 5 days): timing with `--blocks 30` (50 h), tuning with
`--segment-minutes 10`, everything else as above. The paper then reports the reduced sizes.

URSim variant (optional, strongly recommended for the timing claim): copy
`cfg/base_sim_ur5e.json` to `cfg/base_ursim.json` with `robot.backend = "ur_rtde"`,
`robot.host` = URSim address, `robot.port = 30004`, generate a timing campaign from it with
`--base cfg/base_ursim.json --out cfg/campaigns_ursim`, and run it.

Remote inference variant: start `./build/hrc_infer_server --weights models/cbf_ur5e.json
--fifo 80` on the inference device and set `control.learned.remote = true` and its address.

## 8. Protocol latency (~15 min)

```bash
./build/hrc_run --config cfg/base_sim_ur5e.json --duration 700 &      # Modbus 5020, REST 8080
./build/hrc_protocol_bench --modbus-port 5020 --rest-port 8080 --rate-per-min 50 \
    --peak-per-min 112 --duration 600 --backup /media/.../runs
```

## 9. PLC commissioning and porting effort (Windows; hours)

Each timed activity is logged with the chained work log, started and stopped at the moment
it happens:
```
python tools\worklog.py --log logs\plc_siemens_run1.jsonl start siemens_run1 "network configuration"
python tools\worklog.py --log logs\plc_siemens_run1.jsonl start siemens_run1 "OPC-UA client configuration"
...
python tools\worklog.py --log logs\plc_siemens_run1.jsonl stop --note "integration test passed"
python tools\worklog.py --log logs\plc_siemens_run1.jsonl verify
```
Screen recordings of each run (OBS) are strongly recommended and can be deposited. Porting
effort for a new adapter is logged the same way (`logs/effort_<vendor>.jsonl`). The paper
reports these as one engineer's measured times, a potentially optimistic estimate of what
another engineer would need.

## 10. Code metrics

```bash
tools/code_metrics.sh runs
```

## 11. Results and deposit

```bash
python3 analysis/report.py --runs runs --out results
```
`results/results.json` contains every reported quantity and the list of run directories (with
manifest hashes) it was computed from. Deposit: the `runs/` tree (or a tar + SHA-256), `logs/`,
`results/`, and the tagged source commit. Synthetic files from earlier deposits are not
included.
