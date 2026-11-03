# Publishes branch release-3.1 and the given tag of the WSL repository /opt/work/hrc31 to
# github.com/ClaudioUrrea/hrc-architecture, through the Windows clone that holds the stored
# credentials. Never force-pushes, never deletes or moves an existing remote tag.
#   powershell.exe -ExecutionPolicy Bypass -File publish_r31.ps1 -Tag campaign-v4 [-DryRun]
param([Parameter(Mandatory = $true)][string]$Tag, [switch]$DryRun)
$ErrorActionPreference = "Continue"  # git writes progress to stderr; exit codes are checked explicitly
$clone = "C:\Users\Claudio\hrc_tools\r31\gh_clone"
$src = "\\wsl.localhost\Ubuntu-22.04\opt\work\hrc31"
$log = "C:\Users\Claudio\hrc_tools\r31\publish.log"
function Log($m) { $l = "$(Get-Date -Format o) $m"; Add-Content -Path $log -Value $l; Write-Output $l }
Set-Location $clone
git -c safe.directory=* -c "protocol.file.allow=always" fetch --no-tags $src "+refs/heads/release-3.1:refs/heads/release-3.1" "refs/tags/${Tag}:refs/tags/${Tag}" 2>&1 | ForEach-Object { Log "fetch: $_" }
if ($LASTEXITCODE -ne 0) { Log "FAILED fetch"; exit 1 }
$remoteTag = git ls-remote --tags origin "refs/tags/$Tag"
if ($remoteTag) {
  $localSha = git rev-parse "refs/tags/$Tag"
  if ($remoteTag -notmatch $localSha) { Log "FAILED remote tag $Tag exists with a different object; not touching it"; exit 2 }
  Log "tag $Tag already on GitHub (same object)"
}
$refs = @("origin", "refs/heads/release-3.1:refs/heads/release-3.1", "refs/tags/${Tag}:refs/tags/${Tag}")
if ($DryRun) { $pargs = @("push", "--dry-run") + $refs } else { $pargs = @("push") + $refs }
git @pargs 2>&1 | ForEach-Object { Log "push: $_" }
if ($LASTEXITCODE -ne 0) { Log "FAILED push"; exit 3 }
if (-not $DryRun) {
  $pushed = gh api repos/ClaudioUrrea/hrc-architecture --jq .pushed_at
  $obj = gh api "repos/ClaudioUrrea/hrc-architecture/git/ref/tags/$Tag" --jq .object.sha
  Log "PUBLISHED tag=$Tag object=$obj github_pushed_at=$pushed"
}
exit 0
