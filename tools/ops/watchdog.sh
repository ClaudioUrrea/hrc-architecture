#!/bin/bash
# Watchdog for the campaign queues (v2, 2026-10-16: chains queue3 after queue2).
# - queue2 (tuning -> sensitivity -> timing): relaunch ONLY if it died unexpectedly.
# - when queue2 has written QUEUE2 COMPLETE: launch queue3 (comparison campaign, protocol
#   bench, code metrics, report), and relaunch it if it dies unexpectedly.
# - Never (re)launches after a terminal state (COMPLETE / FATAL / FAILED / GAVE UP):
#   those need diagnosis, not a blind retry.
# - Never launches while any runner, hrc_run or protocol bench is alive (no duplicates).
# - Crash-loop guard: 3 launches within 1 h -> gives up and records it.
# Both queues are resumable, so a relaunch continues from the first non-complete run.
LOG=/opt/work/queue2.log
LOG3=/opt/work/queue3.log
WLOG=/opt/work/watchdog.log
STAMPS=/opt/work/.watchdog_relaunches
ts() { date -u +%FT%TZ; }
date +%s > /opt/work/.watchdog_heartbeat

# --- v3 (2026-11-03): release-3.1 queue (queue4). Active while /opt/work/.queue4_enabled exists.
# Same rules as below: relaunch only if queue4 died without a terminal marker; never while a run,
# runner or bench is alive; crash-loop guard (3 launches/h). The launching WSL session must outlive
# the launch: a process started with setsid from a session that exits at once can be killed with it
# (cause of the 26.10 incident, in which queue3 never started), so the watchdog waits 15 s and checks.
if [ -e /opt/work/.queue4_enabled ]; then
  LOG4=/opt/work/queue4.log
  flock -n /tmp/queue2.lock true 2>/dev/null || exit 0
  pgrep -x hrc_run >/dev/null && { echo "$(ts) [q4] lock free but hrc_run alive; not launching" >> "$WLOG"; exit 0; }
  pgrep -x hrc_protocol_be >/dev/null && { echo "$(ts) [q4] lock free but protocol bench alive; not launching" >> "$WLOG"; exit 0; }
  pgrep -f 'run_campaign[.]py' >/dev/null && { echo "$(ts) [q4] lock free but runner alive; not launching" >> "$WLOG"; exit 0; }
  LAST4=$(grep '^===' "$LOG4" 2>/dev/null | tail -1)
  case "$LAST4" in *"QUEUE4 COMPLETE"*|*FATAL*|*"GAVE UP"*) exit 0 ;; esac
  NOW=$(date +%s); S4=/opt/work/.watchdog_relaunches_q4; touch "$S4"
  if [ "$(awk -v n="$NOW" 'n - $1 < 3600' "$S4" | wc -l)" -ge 3 ]; then
    echo "=== watchdog GAVE UP $(ts): 3 launches of queue4 within 1 h (crash loop) - needs diagnosis" >> "$LOG4"
    echo "$(ts) GAVE UP (crash loop) on queue4" >> "$WLOG"; exit 0
  fi
  echo "$NOW" >> "$S4"
  echo "=== watchdog relaunch $(ts): queue4 (last marker: ${LAST4:-none})" >> "$LOG4"
  echo "$(ts) launch /opt/work/queue4.sh" >> "$WLOG"
  setsid -f /opt/work/queue4.sh > /opt/work/queue4_launcher.out 2>&1 < /dev/null
  sleep 15
  flock -n /tmp/queue2.lock true 2>/dev/null && echo "$(ts) [q4] WARNING: queue4 not holding the lock 15 s after launch" >> "$WLOG"
  exit 0
fi

flock -n /tmp/queue2.lock true 2>/dev/null || exit 0          # a queue holds the lock: alive
pgrep -x hrc_run >/dev/null && { echo "$(ts) lock free but hrc_run alive; not launching" >> "$WLOG"; exit 0; }
pgrep -x hrc_protocol_be >/dev/null && { echo "$(ts) lock free but protocol bench alive; not launching" >> "$WLOG"; exit 0; }
pgrep -f 'run_campaign[.]py' >/dev/null && { echo "$(ts) lock free but runner alive; not launching" >> "$WLOG"; exit 0; }

LAST=$(grep '^===' "$LOG" | tail -1)
case "$LAST" in
  *"QUEUE2 COMPLETE"*)
    TARGET=/opt/work/queue3.sh; TLOG=$LOG3; OUT=/opt/work/queue3_launcher.out
    LAST3=$(grep '^===' "$LOG3" 2>/dev/null | tail -1)
    case "$LAST3" in
      *"QUEUE3 COMPLETE"*|*FATAL*|*FAILED*|*"GAVE UP"*) exit 0 ;;
    esac
    WHAT="queue3 (queue2 complete; last queue3 marker: ${LAST3:-none})" ;;
  *FATAL*|*FAILED*|*"GAVE UP"*) exit 0 ;;
  *)
    TARGET=/opt/work/queue2.sh; TLOG=$LOG; OUT=/opt/work/queue2_launcher.out
    WHAT="queue2 (not running, no terminal state; last marker: $LAST)" ;;
esac

NOW=$(date +%s)
touch "$STAMPS"
RECENT=$(awk -v n="$NOW" 'n - $1 < 3600' "$STAMPS" | wc -l)
if [ "$RECENT" -ge 3 ]; then
  echo "=== watchdog GAVE UP $(ts): 3 launches within 1 h (crash loop) — needs diagnosis" >> "$TLOG"
  echo "$(ts) GAVE UP (crash loop) on $TARGET" >> "$WLOG"
  exit 0
fi
echo "$NOW" >> "$STAMPS"
echo "=== watchdog relaunch $(ts): $WHAT" >> "$TLOG"
echo "$(ts) launch $TARGET" >> "$WLOG"
setsid nohup "$TARGET" > "$OUT" 2>&1 < /dev/null &
sleep 15  # v3: keep the launching session alive (26.10 incident)
