# Creates or updates one file on the main branch of github.com/ClaudioUrrea/hrc-architecture
# through the GitHub API (server-side commit, so GitHub's timestamp records when it was published).
#   powershell.exe -ExecutionPolicy Bypass -File publish_record.ps1 -LocalPath <file> -RepoPath docs/freeze/X.md -Message "..."
param([Parameter(Mandatory = $true)][string]$LocalPath,
      [Parameter(Mandatory = $true)][string]$RepoPath,
      [Parameter(Mandatory = $true)][string]$Message)
$ErrorActionPreference = "Continue"
$log = "C:\Users\Claudio\hrc_tools\r31\publish.log"
function Log($m) { $l = "$(Get-Date -Format o) $m"; Add-Content -Path $log -Value $l; Write-Output $l }
$repo = "repos/ClaudioUrrea/hrc-architecture"
$bytes = [IO.File]::ReadAllBytes($LocalPath)
$body = @{ message = $Message; content = [Convert]::ToBase64String($bytes); branch = "main" }
$sha = gh api "$repo/contents/${RepoPath}?ref=main" --jq .sha 2>$null
if ($LASTEXITCODE -eq 0 -and $sha) { $body.sha = $sha.Trim() }
$tmp = [IO.Path]::GetTempFileName()
[IO.File]::WriteAllText($tmp, ($body | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding $false))
$res = gh api -X PUT "$repo/contents/$RepoPath" --input $tmp --jq '.commit.sha + " " + .commit.committer.date'
$rc = $LASTEXITCODE
Remove-Item $tmp
if ($rc -ne 0) { Log "FAILED record $RepoPath"; exit 1 }
Log "RECORD $RepoPath commit=$res"
exit 0
