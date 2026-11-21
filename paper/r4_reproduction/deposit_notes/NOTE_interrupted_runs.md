# Interrupted runs (excluded from every analysis)

`runs_interrupted_excluded.tar.gz` holds the seven run directories that were opened by `hrc_run` but
never closed: they have no `MANIFEST.sha256`, their `manifest.json` still says `"status": "running"`,
and the analysis readers skip them. Each was run again from the start with the same configuration
and seed, and only that complete run is analysed. The directories are deposited as they were left;
nothing in them was edited.

| Directory | Campaign | Event (UTC) |
|---|---|---|
| `2026-11-03T19-19-11.156Z_fault_injection_inj_03` | fault injection | Queue and program terminated about five minutes into the run; no cause recorded; relaunched by the queue watchdog at 19:24. |
| `2026-11-12T00-10-01.075Z_timing_campaign_block_010` | timing | Unexpected restart of the host (Windows System log: Kernel-Power 41 at 00:15:24, bug check 0xD1); relaunched by hand at 00:20. |
| `2026-11-12T20-34-59.496Z_timing_campaign_block_021` | timing | Unexpected restart of the host (Kernel-Power 41 logged at 00:41:09 on 13 Nov); relaunched by the watchdog at 00:44. |
| `2026-11-14T00-36-01.307Z_timing_campaign_block_034` | timing | Unexpected restart of the host (Kernel-Power 41 at 01:25:59, bug check 0xA); relaunched by hand at 01:27. |
| `2026-11-15T22-41-40.376Z_timing_campaign_block_059` | timing | Unexpected restart of the host (Kernel-Power 41 at 23:37:11, bug check 0xA); relaunched by hand at 23:40. |
| `2026-11-17T03-00-46.812Z_timing_campaign_block_074` | timing | Unexpected restart of the host (Kernel-Power 41 logged at 04:34:04); relaunched by hand at 04:36. |
| `2026-11-18T15-32-45.713Z_timing_campaign_block_093` | timing | Queue and program terminated without a restart of the host; no cause recorded; relaunched by the watchdog at 16:04. |

The relaunches are recorded in `queue4.log` (lines beginning `=== manual relaunch` or `=== watchdog relaunch`)
and in `watchdog_launches.log`. The block that preceded the restart of 17 November (block 073) closed
normally and contains the nine retained deadline misses of the timing campaign (manuscript, Section 6.3).
