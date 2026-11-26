# Pre-registration commitment — release 3.x

Published on 26 October 2026, before the comparison campaign started and before any result was reported. It fixes the identity of the design from which the campaigns of manuscript electronics-4587969 (revision 3, MDPI *Electronics*) were run.

The design was frozen on the author's workstation in a local git commit, tagged `campaign-v3`, before the first campaign run (12 October 2026, 15:05 UTC). This file publishes the cryptographic identifiers of that commit and of the campaign executables. The full source tree of the tag will be published in this repository together with the revised manuscript, and anyone can then check it against the values below.

## Frozen design

| Item | Value |
|---|---|
| Tag | `campaign-v3` |
| Commit (SHA-1) | `1a51a5710c9116593b219b16bae3c37fea5aacc5` |
| Tree (SHA-1) | `e5217e615066f0649be89d3531d575d1f0dedda7` |
| Commit date (set locally by the author) | 2026-10-12T12:04:25-03:00 |
| SHA-256 of `git archive --format=tar campaign-v3` (git 2.34.1) | `8cabbea6e6c4925d1af04d8a0b45937c16b438467848edfd0dd9841edb1f3377` |

## Files of the tagged tree (SHA-256 of the file contents)

| File | SHA-256 |
|---|---|
| `cfg/base_sim_ur5e.json` | `95e62a724b7b722835e5429ee1198c36433b9f1e6f358cf1be47e0517fba8b40` |
| `models/cbf_ur5e.json` | `c95fa052b46d44903f2cfc6e8a35d0502611ce69047a6cd45ff068ba5ae8be40` |
| `cfg/campaigns/ablation/plan.csv` | `6b95463cd40637bd8f24912a37ad473a153f668c8d63a22a6cc78fae9d2f19c0` |
| `cfg/campaigns/injection/plan.csv` | `bf03d0dd3942b1f78aca6241751eec0f667e8d4f6a467d8de3cb4b0a0ef2ad9c` |
| `cfg/campaigns/sensitivity/plan.csv` | `0502cb58fa39651c56b6e71b5cf51e70653e3ab314aabb3ce70adf9b6737b88f` |
| `cfg/campaigns/timing/plan.csv` | `85d683413c9bfa9cef4fb56006976ab7115654d05e3464a50a2242e0141f6fd1` |
| `cfg/campaigns/tuning/plan.csv` | `dac5ea1cb70dcadce89b736f4ce7eab8e10f1f603f76c42047736beb22a60dd9` |
| `tools/make_campaigns.py` | `00cf2d10c7f511e9244f9240998807393658f7f634704aadb441a54b7ad8ac09` |
| `analysis/report.py` | `d7ba47572e8e3f99d025afd885c1d801e8596643b75c5bf8e755ed811507e45a` |
| `analysis/timing.py` | `3bdeba644e3ef98c356f0a57ed2289edfeef66cf7540d1758d9c2537b08f9e8c` |
| `analysis/ablation.py` | `e952be1a4059a35f40b69b653df9cb16560953258a56ffda61df9afcb3d7403a` |
| `analysis/faults.py` | `e45c27a521a4ecec30333be05ab295d9887114b44fea802d8aeda9d27619faff` |
| `analysis/baselines.py` | `a96b9972cdfa44a330d5babf0da2a8d93a8e6e6e03c538e761225e3cb198a5dc` |
| `analysis/stats.py` | `32bf3bc8a184e6c9cb39c4885e9fd62385d322e5161ed3535c6fe4f198aa9db0` |
| `analysis/hrc_logs.py` | `e554e1502b9d11dafd8a24dc94d2032ce03523d9d05125404ca1a38f6f54f1f5` |

## Campaign executables (SHA-256)

| Executable | SHA-256 |
|---|---|
| `hrc_run` | `e3deadb08d7cd82f92f4ed45c60dbccd54b83fa60b10fa86728fbcd324b1e92d` |
| `hrc_protocol_bench` | `b445e9b9e88e6ce750afd1158479a69840f94302e29b010cf867789c45b6bfe6` |
| `hrc_conformance` | `df4822d1d0c3f07f3939e6573de2774f93f50d39884c2ceafb77d8b1ba29f96b` |

The run manifests record the build label `3d3d93d91fc8`. The build system captures the commit identifier when the project is configured, not when it is compiled, so the label is stale. `hrc_run` was compiled from the source of the tagged commit (see the manuscript, Section 5.8).

## Still to come

The comparison configurations are generated from the tuning runs by the selection rule frozen in this commit (`analysis/baselines.py`, `tools/make_campaigns.py compare`). They will be committed and tagged `campaign-v3-compare` automatically before the first comparison run, and that tag will also be published.
