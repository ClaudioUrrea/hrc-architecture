# Freeze record: tag `campaign-v4-compare` (release 3.1)

Written by `queue4.sh` on 2026-11-09T01:23:12Z and published through the GitHub API before the first run that depends on it.

| Item | Value |
|---|---|
| Tag | `campaign-v4-compare` |
| Commit | `ab88b07f4bf3bbe0bbddc7554a12d627b85e66f2` |
| Tree | `8b24fb458a065648619d08b3500bfaab31f40796` |
| SHA-256 of `git archive --format=tar campaign-v4-compare` | `fd7a039b99a8b28eb899e27c800ceb0f09de86d79fef1db26008d56b26f6784f` |
| `build/hrc_run` SHA-256 | `3364796a96555feb5ed6df02ed5ed15eb9f2a62de17f75150b4dcab82264573b` |
| `build/hrc_protocol_bench` SHA-256 | `b445e9b9e88e6ce750afd1158479a69840f94302e29b010cf867789c45b6bfe6` |
| `build/hrc_conformance` SHA-256 | `a09b9bdb1320b3c57f8014fe8a8b8885397b1c8946af7d6816f40debfff68b8b` |
| `build/stop_check` SHA-256 | `cd9f47111405c98867d85ae774219864c85c027bffa24db611ef36525873ccdb` |
| Embedded build label | `f5cb16bb2efe` |
| `cfg/base_sim_ur5e.json` SHA-256 | `3e5c93543e60e596915f434266caf9e081c6e3a7926ee725ccb05f161eb9c7dc` |
| `cfg/calibration_v4.json` SHA-256 | `a2e6521aaf9c1f9047f248ade88cd27c022a41e3718cee4b41aff4ab654bc9e1` |
| `cfg/campaigns/ablation/plan.csv` SHA-256 | `6b95463cd40637bd8f24912a37ad473a153f668c8d63a22a6cc78fae9d2f19c0` |
| `cfg/campaigns/calibration/plan.csv` SHA-256 | `05379288ad4daf2476117e78fe78609a003b2148073b384bd66a7e22ef42f7ca` |
| `cfg/campaigns/compare/plan.csv` SHA-256 | `93f7678b0ab99d9aaaedf8028079b228f61600f2aad0e66d78ce018186d17193` |
| `cfg/campaigns/injection/plan.csv` SHA-256 | `bf03d0dd3942b1f78aca6241751eec0f667e8d4f6a467d8de3cb4b0a0ef2ad9c` |
| `cfg/campaigns/sensitivity/plan.csv` SHA-256 | `0502cb58fa39651c56b6e71b5cf51e70653e3ab314aabb3ce70adf9b6737b88f` |
| `cfg/campaigns/timing/plan.csv` SHA-256 | `85d683413c9bfa9cef4fb56006976ab7115654d05e3464a50a2242e0141f6fd1` |
| `cfg/campaigns/tuning/plan.csv` SHA-256 | `b92fc5460c2bd0ff2479ebc978c095adf35e7cd83f533064199fdc8786ee0e7e` |
| `cfg/campaigns/compare/tuning_selection.json` SHA-256 | `3cd5a6c7853df5c433980743affc40bb546747891422b13972c85bdab34b178f` |

Calibration applied (rule in docs/PREREGISTRATION_3.1.md):

```json
{
 "rule": "position_margin = ceil_cm(p99(est_err_closest_m)); Z_d = max(0.04, position_margin)",
 "pooled": {
  "matched_cycles": 179993,
  "p50": 0.06569184362888336,
  "p95": 0.15229803919792173,
  "p99": 0.21114979445934254,
  "max": 0.6651384234428406
 },
 "position_margin_m": 0.22,
 "Z_d_m": 0.22
}
```
