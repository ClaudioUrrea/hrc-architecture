"""Run every analysis and collect the numbers quoted in the paper."""
import argparse, json, importlib

MODULES = ["timing", "boundaries", "protocol", "plc_time", "effort", "faults",
           "reliability", "safety_distance", "conformance", "ablation",
           "tune_baselines", "paired_stats", "cbf_train"]

# Modules whose main() takes a data path rather than no argument.
DATA_ARG = {"reliability": "data/interfailure.csv"}


def main(out):
    results = {}
    for name in MODULES:
        mod = importlib.import_module(name)
        results[name] = mod.main(DATA_ARG[name]) if name in DATA_ARG else mod.main()
    with open(out, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"wrote {out}")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/results.json")
    main(ap.parse_args().out)
