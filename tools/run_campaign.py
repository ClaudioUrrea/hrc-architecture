#!/usr/bin/env python3
"""Run every configuration of a campaign with hrc_run, resumably.

A run whose variant already appears in runs/INDEX.csv with status "complete" is skipped, so the
campaign can be interrupted and resumed. Every run is mirrored to each --backup directory and
verified by hash before the next run starts; the campaign stops if a backup fails, so that no
run ever exists in a single copy.

    python3 tools/run_campaign.py cfg/campaigns/ablation --backup /media/usb/hrc_runs --backup ~/OneDrive/hrc_runs
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def completed(run_root):
    idx = Path(run_root) / "INDEX.csv"
    done = set()
    if idx.exists():
        with open(idx) as f:
            for r in csv.DictReader(f):
                if r["status"] == "complete":
                    done.add((r["experiment"], r["variant"]))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir")
    ap.add_argument("--backup", action="append", default=[], help="backup directory (repeatable, at least one required)")
    ap.add_argument("--run-root", default="runs")
    ap.add_argument("--binary", default=str(ROOT / "build" / "hrc_run"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-no-backup", action="store_true")
    a = ap.parse_args()
    if not a.backup and not a.allow_no_backup:
        sys.exit("refusing to run without at least one --backup directory (use --allow-no-backup for pilots only)")
    plan = list(csv.DictReader(open(Path(a.campaign_dir) / "plan.csv")))
    done = completed(a.run_root)
    log = open(Path(a.run_root) / "campaign_log.txt", "a") if Path(a.run_root).exists() else None
    total = len(plan)
    for i, row in enumerate(plan, 1):
        cpath = Path(row["config"]) if Path(row["config"]).is_absolute() else ROOT / row["config"]
        c = json.loads(cpath.read_text())
        key = (c["experiment"], c["variant"])
        if key in done:
            print(f"[{i}/{total}] skip {c['variant']} (complete)")
            continue
        cmd = [a.binary, "--config", str(cpath), "--run-root", a.run_root]
        for b in a.backup:
            cmd += ["--backup", b]
        print(f"[{i}/{total}] {' '.join(cmd)}", flush=True)
        if a.dry_run:
            continue
        t0 = time.time()
        rc = subprocess.call(cmd, cwd=ROOT)
        msg = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {c['variant']} rc={rc} {time.time() - t0:.0f}s\n"
        if log:
            log.write(msg); log.flush()
        if rc == 4:
            sys.exit(f"backup verification failed after {c['variant']}; stopping so that no run exists in one copy only")
        if rc not in (0,):
            print(f"run {c['variant']} exited with {rc}; continuing (the run directory records its status)")


if __name__ == "__main__":
    main()
