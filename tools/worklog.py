#!/usr/bin/env python3
"""Tamper-evident work log for engineering-effort and PLC-commissioning timing.

Every entry is appended as one JSON line carrying the SHA-256 of the previous line, so an
edited, deleted or reordered entry breaks the chain and `verify` reports it. Timestamps are
taken from the system clock at the moment of the command, not typed in.

    python tools/worklog.py --log logs/effort_kuka.jsonl start kuka "adapter implementation"
    python tools/worklog.py --log logs/effort_kuka.jsonl pause            # breaks are excluded
    python tools/worklog.py --log logs/effort_kuka.jsonl resume
    python tools/worklog.py --log logs/effort_kuka.jsonl stop --note "47 tests passing"
    python tools/worklog.py --log logs/plc_siemens_run1.jsonl start siemens_run1 "network configuration"
    python tools/worklog.py --log logs/effort_kuka.jsonl verify
    python tools/worklog.py --log logs/effort_kuka.jsonl summary

Works on Windows, macOS and Linux (standard library only).
"""
import argparse
import getpass
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def lines(path):
    p = Path(path)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def append(path, entry):
    ls = lines(path)
    entry["prev_sha256"] = hashlib.sha256(ls[-1].encode()).hexdigest() if ls else "0" * 64
    entry["utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry["host"] = platform.node()
    entry["user"] = getpass.getuser()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False))


def verify(path):
    ls = lines(path)
    prev = "0" * 64
    for i, l in enumerate(ls, 1):
        e = json.loads(l)
        if e.get("prev_sha256") != prev:
            print(f"CHAIN BROKEN at line {i}")
            return False
        prev = hashlib.sha256(l.encode()).hexdigest()
    print(f"OK: {len(ls)} entries, chain intact, head {prev}")
    return True


def summary(path):
    ls = [json.loads(l) for l in lines(path)]
    tasks, cur, t_last, active = {}, None, None, False
    for e in ls:
        t = datetime.fromisoformat(e["utc"])
        if active and cur and t_last:
            tasks[cur] = tasks.get(cur, 0) + (t - t_last).total_seconds()
        if e["event"] == "start":
            cur, active = f'{e["subject"]} | {e["task"]}', True
        elif e["event"] == "pause":
            active = False
        elif e["event"] == "resume":
            active = True
        elif e["event"] == "stop":
            active, cur = False, None
        t_last = t
    for k, v in tasks.items():
        print(f"{v / 3600:8.2f} h  {k}")
    print(f"{sum(tasks.values()) / 3600:8.2f} h  total (breaks excluded)")
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("subject"); s.add_argument("task"); s.add_argument("--counted", default="yes")
    for name in ("pause", "resume"):
        sub.add_parser(name)
    s = sub.add_parser("stop"); s.add_argument("--note", default="")
    s = sub.add_parser("note"); s.add_argument("text")
    sub.add_parser("verify")
    sub.add_parser("summary")
    a = ap.parse_args()
    if a.cmd in ("verify", "summary"):
        if a.cmd == "verify":
            sys.exit(0 if verify(a.log) else 1)
        summary(a.log)
        return
    e = {"event": a.cmd}
    if a.cmd == "start":
        e.update({"subject": a.subject, "task": a.task, "counted": a.counted})
    if a.cmd == "stop":
        e["note"] = a.note
    if a.cmd == "note":
        e["text"] = a.text
    append(a.log, e)


if __name__ == "__main__":
    main()
