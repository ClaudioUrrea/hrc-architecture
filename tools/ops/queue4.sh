#!/bin/bash
# queue4 — release 3.1 evaluation (docs/PREREGISTRATION_3.1.md), fully automatic and resumable.
#   0. preflight (root, single instance, backups, space)
#   1. calibration campaign at tag r31-calibration (published before this queue starts)
#   2. calibration rule applied, campaigns generated, commit + tag campaign-v4, build + ctest,
#      binary label checked, freeze record written; tag and record PUBLISHED before step 3
#   3. ablation -> fault_injection -> fault_sensitivity -> tuning
#   4. comparison configs from the tuning rule, commit + tag campaign-v4-compare, PUBLISHED
#   5. comparison -> timing
#   6. protocol bench, code metrics
#   7. report (results.json), stopping check, tag campaign-v4-report, PUBLISHED, results backed up
# Every step is skipped if its output exists, so a relaunch continues where it stopped.
# Terminal markers in the log: "=== QUEUE4 COMPLETE" or "=== FATAL" (needs diagnosis).
set -uo pipefail

ROOT=/opt/work/hrc31
LOG=/opt/work/queue4.log
STATE=/opt/work/queue4_state
LOCK=/tmp/queue2.lock             # shared with queue2/3: one queue at a time
BACKUP_DIRS=(/mnt/e/hrc_backup_A/r31 /mnt/c/hrc_backup_B/r31)
BACKUPS=(--backup /mnt/e/hrc_backup_A/r31 --backup /mnt/c/hrc_backup_B/r31)
MIN_FREE_GB=25
OWNER=laudio
GIT_ID=(-c "user.name=Claudio Urrea" -c "user.email=claudio.urrea@usach.cl")
PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
PUBDIR='C:\Users\Claudio\hrc_tools\r31'
RECDIR_WIN='C:\Users\Claudio\Desktop\A\03_Trabajo_R4\Release_3.1\freeze'
RECDIR=/mnt/c/Users/Claudio/Desktop/A/03_Trabajo_R4/Release_3.1/freeze
TRAILER=$'\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01UU1Ewb2xt5RVdRKDWmbnNv'

ts()  { date -u +%FT%TZ; }
say() { echo "$*" >> "$LOG"; }
die() { say "=== FATAL $(ts): $*"; exit 1; }
GIT=(git -c safe.directory="$ROOT" -C "$ROOT")
UGIT=(sudo -u "$OWNER" git -C "$ROOT" "${GIT_ID[@]}")
AS_OWNER=(sudo -u "$OWNER")

free_gb() { df -BG --output=avail "$1" | tail -1 | tr -dc '0-9'; }
check_space() {
  local d g
  for d in "${BACKUP_DIRS[@]}" "$ROOT/runs"; do
    g=$(free_gb "$d")
    [ "${g:-0}" -ge "$MIN_FREE_GB" ] || { say "=== FATAL $(ts): only ${g}G free at $d (< ${MIN_FREE_GB}G)"; return 1; }
  done
}
completeness() {  # prints "n/N" for a campaign directory
  python3 - "$1" <<'PY'
import csv, json, sys
from pathlib import Path
camp = sys.argv[1]; root = Path("/opt/work/hrc31")
keys = []
for row in csv.DictReader(open(root / f"cfg/campaigns/{camp}/plan.csv")):
    p = Path(row["config"]); p = p if p.is_absolute() else root / p
    c = json.loads(p.read_text()); keys.append((c["experiment"], c["variant"]))
idx = root / "runs/INDEX.csv"
done = {(r["experiment"], r["variant"]) for r in csv.DictReader(open(idx)) if r.get("status") == "complete"} if idx.exists() else set()
print(f"{sum(k in done for k in keys)}/{len(keys)}")
PY
}
run_campaign() {  # name
  local c=$1 n
  check_space || exit 1
  n=$(completeness "$c")
  if [ "${n%/*}" = "${n#*/}" ]; then say "    $c already complete ($n)"; return 0; fi
  say "=== $c start $(ts) ($n complete)"
  python3 tools/run_campaign.py "cfg/campaigns/$c" "${BACKUPS[@]}" >> "$LOG" 2>&1 \
    || die "$c: runner aborted (backup verification?) at $(completeness "$c")"
  n=$(completeness "$c")
  if [ "${n%/*}" != "${n#*/}" ]; then  # one retry pass for runs that ended interrupted or failed
    say "    $c: $n complete after the first pass; one retry pass $(ts)"
    python3 tools/run_campaign.py "cfg/campaigns/$c" "${BACKUPS[@]}" >> "$LOG" 2>&1 \
      || die "$c: runner aborted on the retry pass at $(completeness "$c")"
    n=$(completeness "$c")
  fi
  say "=== $c done $(ts) ($n complete)"
  # a run that ended interrupted/failed is recorded as such; it is retried once by a relaunch
  [ "${n%/*}" = "${n#*/}" ] || say "    WARNING: $c has non-complete runs ($n); see runs/INDEX.csv"
}
publish_tag() {  # tag -> pushes branch release-3.1 + tag through the Windows clone (3 attempts)
  local t=$1 i
  [ -e "$STATE/published_$t" ] && return 0
  for i in 1 2 3; do
    if "$PS" -NoProfile -ExecutionPolicy Bypass -File "$PUBDIR\\publish_r31.ps1" -Tag "$t" >> "$LOG" 2>&1; then
      date -u +%FT%TZ > "$STATE/published_$t"; say "    published tag $t ($(ts))"; return 0
    fi
    say "    publish attempt $i for $t failed; retrying in 120 s"; sleep 120
  done
  return 1
}
publish_record() {  # local-linux-path repo-path message
  local f=$1 rp=$2 msg=$3 key i
  key=$(echo "$rp" | tr '/' '_')
  [ -e "$STATE/record_$key" ] && return 0
  mkdir -p "$RECDIR" && cp "$f" "$RECDIR/" || return 1
  for i in 1 2 3; do
    if "$PS" -NoProfile -ExecutionPolicy Bypass -File "$PUBDIR\\publish_record.ps1" -LocalPath "$RECDIR_WIN\\$(basename "$f")" \
         -RepoPath "$rp" -Message "$msg" >> "$LOG" 2>&1; then
      date -u +%FT%TZ > "$STATE/record_$key"; say "    published record $rp ($(ts))"; return 0
    fi
    say "    record attempt $i for $rp failed; retrying in 120 s"; sleep 120
  done
  return 1
}
has_label() { strings -a "$ROOT/build/hrc_run" | grep -qx "$1"; }   # exact embedded build label
build_and_test() {  # builds at HEAD (configure + compile as owner), runs ctest, checks the label
  local want; want=$("${GIT[@]}" rev-parse --short=12 HEAD)
  "${AS_OWNER[@]}" rm -rf "$ROOT/build" 2>/dev/null || rm -rf "$ROOT/build"
  "${AS_OWNER[@]}" cmake -S "$ROOT" -B "$ROOT/build" -DCMAKE_BUILD_TYPE=Release >> "$LOG" 2>&1 || return 1
  "${AS_OWNER[@]}" make -C "$ROOT/build" -j8 >> "$LOG" 2>&1 || return 1
  # tests run as the owner: with fs.protected_regular, root cannot overwrite the owner's /tmp files
  ( cd "$ROOT/build" && "${AS_OWNER[@]}" ctest --output-on-failure ) >> "$LOG" 2>&1 || { say "    ctest FAILED"; return 1; }
  has_label "$want" || { say "    binary does not embed the label $want (clean HEAD)"; return 1; }
  say "    build OK at $want; ctest passed; hrc_run sha256=$(sha256sum "$ROOT/build/hrc_run" | cut -d' ' -f1)"
}
freeze_record() {  # tag outfile
  local t=$1 out=$2
  {
    echo "# Freeze record: tag \`$t\` (release 3.1)"
    echo
    echo "Written by \`queue4.sh\` on $(ts) and published through the GitHub API before the first run that depends on it."
    echo
    echo "| Item | Value |"
    echo "|---|---|"
    echo "| Tag | \`$t\` |"
    echo "| Commit | \`$("${GIT[@]}" rev-parse "$t^{commit}")\` |"
    echo "| Tree | \`$("${GIT[@]}" rev-parse "$t^{tree}")\` |"
    echo "| SHA-256 of \`git archive --format=tar $t\` | \`$("${GIT[@]}" archive --format=tar "$t" | sha256sum | cut -d' ' -f1)\` |"
    for b in hrc_run hrc_protocol_bench hrc_conformance stop_check; do
      [ -x "$ROOT/build/$b" ] && echo "| \`build/$b\` SHA-256 | \`$(sha256sum "$ROOT/build/$b" | cut -d' ' -f1)\` |"
    done
    echo "| Embedded build label | \`$(git -c safe.directory="$ROOT" -C "$ROOT" rev-parse --short=12 'campaign-v4^{commit}' 2>/dev/null || echo n/a)\` |"
    for f in cfg/base_sim_ur5e.json cfg/calibration_v4.json cfg/campaigns/*/plan.csv cfg/campaigns/compare/tuning_selection.json; do
      [ -e "$ROOT/$f" ] && echo "| \`$f\` SHA-256 | \`$(sha256sum "$ROOT/$f" | cut -d' ' -f1)\` |"
    done
    echo
    if [ -e "$ROOT/cfg/calibration_v4.json" ]; then
      echo "Calibration applied (rule in docs/PREREGISTRATION_3.1.md):"
      echo
      echo '```json'
      python3 -c "import json;d=json.load(open('$ROOT/cfg/calibration_v4.json'));d.pop('runs',None);print(json.dumps(d,indent=1))"
      echo '```'
    fi
  } > "$out"
}

# ------------------------------------------------------------------ 0. preflight
exec 9>"$LOCK" || { echo "cannot open lock"; exit 1; }
flock -n 9 || { echo "a queue is already running"; exit 1; }
mkdir -p "$STATE" "$ROOT/runs" "${BACKUP_DIRS[@]}"
cd "$ROOT" || exit 1
say "=== queue4 launch $(ts) host=$(hostname) user=$(id -un)"
[ "$(id -u)" -eq 0 ] || die "must run as root (real-time policy, backups)"
for d in "${BACKUP_DIRS[@]}"; do [ -d "$d" ] && [ -w "$d" ] || die "backup dir unavailable: $d"; done
check_space || exit 1
[ -z "$("${GIT[@]}" status --porcelain)" ] || die "git working tree not clean"
"${GIT[@]}" rev-parse -q --verify refs/tags/r31-calibration >/dev/null || die "tag r31-calibration missing"
[ -e "$STATE/published_r31-calibration" ] || publish_tag r31-calibration || die "r31-calibration not published"

# ------------------------------------------------------------------ 1-2. calibration and freeze
if ! "${GIT[@]}" rev-parse -q --verify refs/tags/campaign-v4 >/dev/null; then
  [ "$("${GIT[@]}" rev-parse HEAD)" = "$("${GIT[@]}" rev-parse 'r31-calibration^{commit}')" ] || die "HEAD is not r31-calibration"
  has_label "$("${GIT[@]}" rev-parse --short=12 HEAD)" || { build_and_test || die "build/test at r31-calibration failed"; }
  run_campaign calibration
  n=$(completeness calibration); [ "${n%/*}" = "${n#*/}" ] || die "calibration incomplete ($n): rule not applied"
  "${AS_OWNER[@]}" python3 tools/calibrate_position_margin.py --runs runs --apply >> "$LOG" 2>&1 || die "calibration rule failed"
  "${AS_OWNER[@]}" python3 tools/make_campaigns.py all >> "$LOG" 2>&1 || die "make_campaigns all failed"
  "${UGIT[@]}" add -A cfg >> "$LOG" 2>&1 || die "git add failed"
  "${UGIT[@]}" commit -q -m "Freeze campaign-v4: calibration rule applied, campaigns generated (docs/PREREGISTRATION_3.1.md)$TRAILER" || die "commit failed"
  "${UGIT[@]}" tag campaign-v4 || die "tag campaign-v4 failed"
  say "    frozen: campaign-v4 = $("${GIT[@]}" rev-parse HEAD); $(python3 -c "import json;d=json.load(open('cfg/calibration_v4.json'));print('margin',d['position_margin_m'],'Z_d',d['Z_d_m'],'p99',round(d['pooled']['p99'],4))")"
fi
V4=$("${GIT[@]}" rev-parse 'campaign-v4^{commit}')
if [ ! -e "$STATE/built_v4" ]; then
  [ "$("${GIT[@]}" rev-parse HEAD)" = "$V4" ] || die "HEAD is not campaign-v4 before the build"
  build_and_test || die "build/test at campaign-v4 failed"
  touch "$STATE/built_v4"
fi
has_label "$("${GIT[@]}" rev-parse --short=12 "$V4")" || die "binary label is not campaign-v4"
freeze_record campaign-v4 "$STATE/FREEZE_campaign-v4.md"
publish_tag campaign-v4 || die "publication of campaign-v4 failed: campaigns not started"
publish_record "$STATE/FREEZE_campaign-v4.md" docs/freeze/FREEZE_campaign-v4.md \
  "Freeze record campaign-v4 (release 3.1), published before the first campaign run" || die "freeze record not published"
say "=== preflight OK $(ts) | frozen at campaign-v4 $V4"

# ------------------------------------------------------------------ 3. campaigns before the comparison
for c in ablation injection sensitivity tuning; do run_campaign "$c"; done

# ------------------------------------------------------------------ 4. comparison configs
if ! "${GIT[@]}" rev-parse -q --verify refs/tags/campaign-v4-compare >/dev/null; then
  mkdir -p results && chown "$OWNER": results
  "${AS_OWNER[@]}" python3 - >> "$LOG" 2>&1 <<'PY' || die "tuning selection failed"
import json, sys
sys.path.insert(0, "analysis")
import baselines
sel = baselines.tune("runs", "results/tuning_selection.json")
print("    tuning selection:", json.dumps(sel))
PY
  "${AS_OWNER[@]}" python3 tools/make_campaigns.py compare --selection results/tuning_selection.json >> "$LOG" 2>&1 || die "make_campaigns compare failed"
  "${AS_OWNER[@]}" cp results/tuning_selection.json cfg/campaigns/compare/tuning_selection.json
  "${UGIT[@]}" add -A cfg/campaigns/compare || die "git add compare failed"
  "${UGIT[@]}" commit -q -m "Comparison campaign generated from the tuning selection (rule fixed at r31-calibration)$TRAILER" || die "commit compare failed"
  "${UGIT[@]}" tag campaign-v4-compare || die "tag campaign-v4-compare failed"
  say "    compare generated: $(tail -n +2 cfg/campaigns/compare/plan.csv | wc -l) runs; tag campaign-v4-compare"
fi
freeze_record campaign-v4-compare "$STATE/FREEZE_campaign-v4-compare.md"
publish_tag campaign-v4-compare || die "publication of campaign-v4-compare failed: comparison not started"
publish_record "$STATE/FREEZE_campaign-v4-compare.md" docs/freeze/FREEZE_campaign-v4-compare.md \
  "Freeze record campaign-v4-compare (release 3.1), published before the first comparison run" || die "compare record not published"

# ------------------------------------------------------------------ 5. comparison and timing
run_campaign compare
run_campaign timing

# ------------------------------------------------------------------ 6. protocol bench, code metrics (as in 3.0)
if ! ls runs/*_protocol_bench/MANIFEST.sha256 >/dev/null 2>&1; then
  check_space || exit 1
  say "=== protocol bench start $(ts)"
  ./build/hrc_run --config cfg/base_sim_ur5e.json --variant protocol_host --duration 700 \
      --run-root runs "${BACKUPS[@]}" --notes "protocol bench host (RUNBOOK 8)" >> "$LOG" 2>&1 &
  HOST=$!
  sleep 20
  kill -0 "$HOST" 2>/dev/null || die "protocol bench: host hrc_run exited early"
  ./build/hrc_protocol_bench --host 127.0.0.1 --modbus-port 5020 --rest-port 8080 --rate-per-min 50 \
      --peak-per-min 112 --duration 600 --run-root runs "${BACKUPS[@]}" >> "$LOG" 2>&1 || die "protocol bench failed"
  wait "$HOST"
  say "=== protocol bench done $(ts)"
fi
if ! ls runs/*_code_metrics/MANIFEST.sha256 >/dev/null 2>&1; then
  CM=$("${AS_OWNER[@]}" tools/code_metrics.sh runs 2>> "$LOG") || die "code_metrics.sh failed"
  chmod -R a-w "$CM"
  for b in "${BACKUP_DIRS[@]}"; do
    cp -a "$CM" "$b/" && ( cd "$b/$(basename "$CM")" && sha256sum -c --quiet MANIFEST.sha256 ) || die "code metrics backup failed"
  done
  say "=== code metrics done $(ts): $CM"
fi

# ------------------------------------------------------------------ 7. report
say "=== report start $(ts)"
"${AS_OWNER[@]}" mkdir -p results
python3 analysis/report.py --runs runs --out results >> "$LOG" 2>&1 || die "analysis/report.py failed"
python3 tools/stop_samples.py --runs runs --experiment baseline_compare --every 200 > results/stop_samples_compare.csv 2>> "$LOG" \
  || die "stop_samples failed"
./build/stop_check --decel 3.0 --T_r "$(python3 -c "import json;print(json.load(open('cfg/base_sim_ur5e.json'))['ssm']['T_r'])")" \
  --a_stop "$(python3 -c "import json;print(json.load(open('cfg/base_sim_ur5e.json'))['ssm']['a_stop'])")" \
  < results/stop_samples_compare.csv > results/stop_check_compare.csv 2> results/stop_check_summary.txt || die "stop_check failed"
( cd results && sha256sum results.json tuning_selection.json stop_check_compare.csv stop_check_summary.txt > SHA256SUMS )
chown -R "$OWNER": results
if ! "${GIT[@]}" rev-parse -q --verify refs/tags/campaign-v4-report >/dev/null; then
  "${UGIT[@]}" tag campaign-v4-report || die "tag campaign-v4-report failed"
fi
RS=results_v4_$(date -u +%Y%m%dT%H%M%SZ)
for b in "${BACKUP_DIRS[@]}"; do
  mkdir -p "$b/$RS" && cp -a results/. "$b/$RS/" && ( cd "$b/$RS" && sha256sum -c --quiet SHA256SUMS ) \
    || say "    WARNING: results copy to $b not verified"
done
freeze_record campaign-v4-report "$STATE/FREEZE_campaign-v4-report.md"
echo "| \`results/results.json\` SHA-256 | \`$(sha256sum results/results.json | cut -d' ' -f1)\` |" >> "$STATE/FREEZE_campaign-v4-report.md"
publish_tag campaign-v4-report || say "    WARNING: campaign-v4-report not published (publish manually)"
publish_record "$STATE/FREEZE_campaign-v4-report.md" docs/freeze/FREEZE_campaign-v4-report.md \
  "Results record campaign-v4-report (release 3.1)" || say "    WARNING: report record not published"
say "    results.json sha256=$(sha256sum results/results.json | cut -d' ' -f1)"
say "=== QUEUE4 COMPLETE $(ts)"
