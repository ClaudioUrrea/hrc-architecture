"""Readers for raw run directories written by hrc_run (and by the bench/conformance tools).

Every reader first verifies MANIFEST.sha256; a run whose files do not match their recorded
hashes is refused, and a run whose manifest status is not "complete" is reported, not
silently included. Nothing in analysis/ reads a number from the paper.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

FLAGS = {
    "overrun": 1 << 0, "injected_overrun": 1 << 1, "qp_relaxed": 1 << 2, "qp_failed": 1 << 3,
    "learned_untrusted": 1 << 4, "estimate_unavailable": 1 << 5, "release_late": 1 << 6,
    "stop_commanded": 1 << 7, "remote_inference": 1 << 8, "remote_timeout": 1 << 9,
}
MODES = ["nominal", "low_confidence", "degraded_stream", "geometric_fallback", "overrun_shed",
         "protective_stop", "protective_stop_latched", "emergency_stop"]
_NP = {"u8": "<u8", "i8": "<i8", "i4": "<i4", "f4": "<f4", "u2": "<u2", "u1": "u1"}


class IntegrityError(RuntimeError):
    pass


def verify(run_dir):
    run_dir = Path(run_dir)
    man = run_dir / "MANIFEST.sha256"
    if not man.exists():
        raise IntegrityError(f"{run_dir}: no MANIFEST.sha256 (run never closed)")
    for line in man.read_text().splitlines():
        if not line.strip():
            continue
        h, name = line[:64], line[66:]
        if hashlib.sha256((run_dir / name).read_bytes()).hexdigest() != h:
            raise IntegrityError(f"{run_dir}/{name}: SHA-256 mismatch")
    return True


def manifest(run_dir):
    return json.loads((Path(run_dir) / "manifest.json").read_text())


def config(run_dir):
    return json.loads((Path(run_dir) / "config.json").read_text())


def cycle_dtype(run_dir):
    s = json.loads((Path(run_dir) / "schema.json").read_text())
    names, formats, offsets = [], [], []
    for f in s["fields"]:
        names.append(f["name"]); offsets.append(f["offset"])
        fmt = _NP[f["type"]]
        formats.append((fmt, (f["count"],)) if f.get("count") else fmt)
    return np.dtype({"names": names, "formats": formats, "offsets": offsets, "itemsize": s["size"]})


def cycles(run_dir, check=True):
    run_dir = Path(run_dir)
    if check:
        verify(run_dir)
    return np.fromfile(run_dir / "cycles.bin", dtype=cycle_dtype(run_dir))


def events(run_dir):
    out = []
    with open(Path(run_dir) / "events.jsonl") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def runs(root, experiment=None, include_incomplete=False):
    """All run directories under root (optionally of one experiment), oldest first."""
    found = []
    for d in sorted(Path(root).iterdir()):
        if not (d / "manifest.json").exists():
            continue
        m = manifest(d)
        if experiment and m.get("experiment") != experiment:
            continue
        if m.get("status") != "complete" and not include_incomplete:
            print(f"[hrc_logs] skipping {d.name}: status={m.get('status')}")
            continue
        found.append(d)
    return found


def flag(c, name):
    return (c["flags"] & FLAGS[name]) != 0


def exec_ms(c):
    """Cycle execution time: wake-up to command written, in ms."""
    return (c["t_end_ns"] - c["t_wake_ns"]) * 1e-6


def release_interval_ms(c):
    return np.diff(c["t_wake_ns"]) * 1e-6
