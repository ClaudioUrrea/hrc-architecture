#!/bin/bash
# Status of the release-3.1 queue (read-only).
ROOT=/opt/work/hrc31
echo "now (UTC): $(date -u +%FT%TZ)"
echo "queue4 enabled: $([ -e /opt/work/.queue4_enabled ] && echo yes || echo no)   lock held: $(flock -n /tmp/queue2.lock true 2>/dev/null && echo no || echo yes)"
echo "--- last markers"
grep '^===' /opt/work/queue4.log 2>/dev/null | tail -6
echo "--- running"
pgrep -a hrc_run | cut -c1-160 || echo "(no hrc_run)"
echo "--- completeness"
for c in calibration ablation injection sensitivity tuning compare timing; do
  [ -r "$ROOT/cfg/campaigns/$c/plan.csv" ] || { echo "$c: not generated yet"; continue; }
  python3 - "$c" <<'PY'
import csv, json, sys
from pathlib import Path
camp = sys.argv[1]; root = Path("/opt/work/hrc31")
keys = []
for row in csv.DictReader(open(root / f"cfg/campaigns/{camp}/plan.csv")):
    p = Path(row["config"]); p = p if p.is_absolute() else root / p
    c = json.loads(p.read_text()); keys.append((c["experiment"], c["variant"]))
idx = root / "runs/INDEX.csv"
rows = list(csv.DictReader(open(idx))) if idx.exists() else []
done = {(r["experiment"], r["variant"]) for r in rows if r.get("status") == "complete"}
bad = [r["variant"] for r in rows if (r["experiment"], r["variant"]) in set(keys) and r.get("status") != "complete"]
print(f"{camp}: {sum(k in done for k in keys)}/{len(keys)} complete" + (f"; non-complete records: {len(bad)}" if bad else ""))
PY
done
echo "--- published"
ls /opt/work/queue4_state 2>/dev/null | tr '\n' ' '; echo
echo "--- tags"
git -c safe.directory=$ROOT -C $ROOT tag | grep -E 'r31|v4' | tr '\n' ' '; echo
echo "--- disk"
df -h /mnt/e /mnt/c / | tail -3
echo "--- watchdog"
tail -3 /opt/work/watchdog.log
