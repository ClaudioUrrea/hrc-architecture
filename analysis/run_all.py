"""Run every analysis and collect the numbers quoted in the paper."""
import argparse, json, importlib
from pathlib import Path

MODULES = ["timing", "protocol", "plc_time", "effort", "faults",
           "reliability", "ablation", "paired_stats"]


def main(out):
    results = {}
    for name in MODULES:
        mod = importlib.import_module(name)
        results[name] = mod.main() if name != "reliability" else mod.main("data/interfailure.csv")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"wrote {out}")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/results.json")
    main(ap.parse_args().out)
