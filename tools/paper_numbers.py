#!/usr/bin/env python3
"""Turn results/results.json into LaTeX macros, so that the manuscript prints only numbers
computed from raw runs.

    python3 tools/paper_numbers.py results/results.json > paper/numbers.tex

In the manuscript: \\input{numbers} and write e.g. "median \\TimingExecMedian\\,ms". A missing
quantity expands to a red "??" so it cannot go unnoticed. The header of numbers.tex records the
SHA-256 of results.json it was generated from.
"""
import hashlib
import json
import re
import sys
from pathlib import Path


def macro_name(path):
    parts = re.split(r"[^A-Za-z0-9]+", path)
    name = "".join(p[:1].upper() + p[1:] for p in parts if p)
    words = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
    name = re.sub(r"\d", lambda m: words[int(m.group())], name)  # TeX macro names: letters only
    return name


def fmt(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}".replace(",", "{,}")
    if isinstance(v, float):
        a = abs(v)
        if a == 0:
            return "0"
        if a >= 100:
            return f"{v:.0f}"
        if a >= 10:
            return f"{v:.1f}"
        if a >= 1:
            return f"{v:.2f}"
        if a >= 0.01:
            return f"{v:.3f}"
        return f"{v:.2e}".replace("e-0", r"\times10^{-").replace("e-", r"\times10^{-") + "}"
    return str(v)


def walk(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("inputs", "inventory", "items", "rows", "curve"):
                continue
            walk(f"{prefix} {k}", v, out)
    elif isinstance(obj, list):
        if len(obj) == 2 and all(isinstance(x, (int, float)) or x is None for x in obj):
            out[macro_name(prefix + " lo")] = fmt(obj[0]) if obj[0] is not None else None
            out[macro_name(prefix + " hi")] = fmt(obj[1]) if obj[1] is not None else None
    elif obj is not None:
        out[macro_name(prefix)] = fmt(obj)


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "results/results.json")
    res = json.loads(src.read_text())
    out = {}
    for section in ("timing", "ablation", "fault_injection", "faults_in_timing_campaign", "fault_sensitivity",
                    "tuning_selection", "protocol", "conformance", "cbf_training"):
        if res.get(section):
            walk(section, res[section], out)
    # baseline comparison rows
    for r in (res.get("baseline_comparison") or {}).get("rows", []):
        walk(f"compare {r['baseline']} {r['endpoint']}", {k: v for k, v in r.items() if k not in ("baseline", "endpoint")}, out)
    print(f"% generated from {src} sha256 {hashlib.sha256(src.read_bytes()).hexdigest()}")
    print(r"\providecommand{\missingnum}{\textcolor{red}{??}}")
    for k, v in sorted(out.items()):
        val = v if v is not None else r"\missingnum"
        print(f"\\newcommand{{\\{k}}}{{{val}}}")


if __name__ == "__main__":
    main()
