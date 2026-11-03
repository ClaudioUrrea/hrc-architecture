# Operating scripts of the release-3.1 campaigns (copies; the running copies live outside the tree)

- `queue4.sh` (`/opt/work/queue4.sh`, run as root in WSL): calibration -> freeze (tag `campaign-v4`) -> publication ->
  ablation -> injection -> sensitivity -> tuning -> comparison configs (tag `campaign-v4-compare`) -> publication ->
  comparison -> timing -> protocol bench -> code metrics -> report (tag `campaign-v4-report`). Resumable.
- `watchdog.sh` (Windows scheduled task every 10 min, `wsl.exe -u root -e /opt/work/watchdog.sh`): relaunches a queue
  that died without a terminal marker; never after COMPLETE/FATAL; crash-loop guard.
- `status4.sh`: read-only status.
- `publish_r31.ps1`, `publish_record.ps1` (Windows side, stored GitHub credentials): push branch `release-3.1` with a
  tag (never force, never moves an existing tag); write a record file on `main` through the GitHub API.
