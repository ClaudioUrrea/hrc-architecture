# Reproducing the numbers and figures of the round-3 revision (release 3.0 records)

This folder closes a gap noted by Reviewer 2 in round 4. Appendix B of the round-3 manuscript
named `extra_analysis` and `below_floor_events`, but these scripts were not in the tagged tree.
They are added here **unchanged** (SHA-256 below), together with the two scripts that turn the
results files into the macros and figures of the manuscript. Nothing in the tags
`campaign-v3`, `campaign-v3-compare` or `campaign-v3-report` is modified.

| Script | SHA-256 | Role |
|---|---|---|
| `extra_analysis.py` | `bea395f8324ff085759ca0f2a9fb12903ee4f3dc084ad8337015fcf0bb58bba4` | supplementary analyses → `results_extra.json` (not pre-registered) |
| `below_floor_events.py` | `e74339fa788783870b2755e82b9e0242a2fe5155b3815943c48d8216953f1a02` | supplementary S6 → `below_floor.json` (not pre-registered) |
| `make_numbers.py` | `a85a29f5ad92923203b3e168a35c34de3ba7d6ac732df74ad545c528137b60f9` | results files → LaTeX macros used in the text |
| `make_figures.py` | `7585b36f9c2954ee9d1b9d5c8ab260325f9f8f37f471138d31eb7612aca48a70` | results files → figures |

## Route from raw records to every reported output

Requirements: Python 3.10+, `numpy`, `scipy`, `matplotlib`.

```bash
# 0. this repository, on a branch that contains paper/r3_reproduction (e.g. main)
git clone https://github.com/ClaudioUrrea/hrc-architecture.git && cd hrc-architecture
pip install -r requirements.txt matplotlib
# 1. raw records: download https://doi.org/10.6084/m9.figshare.34845711 and extract every
#    campaign archive into one directory RUNS/ (one sub-directory per run, each with its
#    manifest.json; the deposit README lists the archives and their MD5)
# 2. the analysis code exactly as pre-registered, in a second worktree
git worktree add ../hrc-r3 campaign-v3-report
# 3. pre-registered results (main text)
python3 ../hrc-r3/analysis/report.py --runs RUNS --out results           # -> results/results.json
# 4. supplementary results (Appendix B); --repo points at the tagged worktree, whose
#    analysis/hrc_logs.py and analysis/faults.py the scripts import
python3 paper/r3_reproduction/extra_analysis.py --repo ../hrc-r3 --runs RUNS \
    --results results/results.json --out results/results_extra.json
python3 paper/r3_reproduction/below_floor_events.py --repo ../hrc-r3 --runs RUNS --out results/below_floor.json
# 5. macros and figures of the manuscript
python3 paper/r3_reproduction/make_numbers.py --results results/results.json \
    --extra results/results_extra.json --below results/below_floor.json --out numbers/r3_numbers.tex
python3 paper/r3_reproduction/make_figures.py --results results/results.json \
    --extra results/results_extra.json --out figures/
```

**Checking step 3.** The deposited `results.json` has SHA-256
`b50c6cfc3265591231b573527c1d5a88b2811bf6d46a79d562e0ac5f51de91e4`. A regenerated file never
has the same hash, because it records its generation time (`generated_utc`) and the path of the
runs (`runs_root`). It also lists every run directory present under `RUNS/` (`inventory`).
Compare everything else:

```bash
python3 - results/results.json DEPOSIT/results.json <<'EOF'
import json, sys
a, b = (json.load(open(f)) for f in sys.argv[1:])
for d in (a, b):
    for k in ("generated_utc", "runs_root"):
        d.pop(k, None)
print("identical" if a == b else "DIFFERENT: " + ", ".join(k for k in a if a.get(k) != b.get(k)))
EOF
```
