# Build of manuscript R4 on the Windows host (MiKTeX + Windows Python), at idle priority so that a
# running campaign is not disturbed. Regenerates numbers, chronology and figures from data\ and
# compiles the manuscript (3 passes). Letters: scripts\build_letters_r4.ps1.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_r4.ps1 [-SkipFigures]
param([switch]$SkipFigures)
$ErrorActionPreference = 'Continue'
(Get-Process -Id $PID).PriorityClass = 'Idle'   # inherited by python and pdflatex
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
New-Item -ItemType Directory -Force data, numbers, figures | Out-Null

# queue log (chronology); read-only copy from WSL
$q = wsl -u root -e bash -c "cat /opt/work/queue4.log 2>/dev/null"
if ($q) { $q | Set-Content -Encoding utf8 data\queue4.log }

python scripts\make_numbers.py --results data\results.json --extra data\results_extra.json `
  --results-r30 data_r30\results.json --stop-summary data\stop_check_summary.txt `
  --stop-csv data\stop_check_compare.csv --conformance-r31 data\conformance_r31 `
  --miss-detail data\timing_miss_detail.json --supp data\results_supp.json --out numbers
python scripts\make_chronology.py --log data\queue4.log --out numbers\r4_chronology.tex
if (-not $SkipFigures) {
  python scripts\make_figures.py --results data\results.json --extra data\results_extra.json --out figures
}
foreach ($i in 1..3) { pdflatex -interaction=nonstopmode P2_Electronics_R4.tex *> build.log }
$err = Select-String -Path build.log -Pattern '^!' 
if ($err) { "LaTeX errors:"; $err | ForEach-Object { $_.Line } } else { "compiled: P2_Electronics_R4.pdf" }
Select-String -Path build.log -Pattern 'undefined' | Select-Object -First 10 | ForEach-Object { "  " + $_.Line }
$tex = Get-Content P2_Electronics_R4.tex -Raw
$pend = ([regex]::Matches($tex, '\\pending\{')).Count
$nums = Get-Content numbers\r4_numbers.tex -Raw
$miss = ([regex]::Matches($nums, '\{\\missingnum\}')).Count
"pending items in the manuscript: $pend; macros still missing (??): $miss"
