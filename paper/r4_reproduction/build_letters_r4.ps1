# Letters of revision R4 (cover letter to the Editor, response to Reviewer 2). Run after build_r4.ps1:
# section, table and equation numbers come from ..\P2_Electronics_R4.aux through xr, and reference
# numbers from letters\ms_bibnums.tex, extracted here from the same .aux.
$ErrorActionPreference = 'Continue'
(Get-Process -Id $PID).PriorityClass = 'Idle'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$aux = Get-Content P2_Electronics_R4.aux
$bib = foreach ($l in $aux) {
  if ($l -match '^\\bibcite\{([^}]*)\}\{\{?(\d+)') { "\expandafter\def\csname msref@$($Matches[1])\endcsname{$($Matches[2])}" }
}
$bib | Set-Content -Encoding ascii letters\ms_bibnums.tex
Set-Location letters
foreach ($L in 'Response_Reviewer2_R4', 'Cover_letter_Editor_R4') {
  foreach ($i in 1..2) { pdflatex -interaction=nonstopmode "$L.tex" *> "$L.build.log" }
  $e = Select-String -Path "$L.build.log" -Pattern '^!'
  if ($e) { "LaTeX errors in ${L}:"; $e | ForEach-Object { '  ' + $_.Line } } else { "compiled: letters\$L.pdf" }
  Select-String -Path "$L.build.log" -Pattern 'Reference .* undefined' | ForEach-Object { "  [$L] " + $_.Line }
  $t = Get-Content "$L.tex" -Raw
  "  pending: " + ([regex]::Matches($t, '\\pending\{')).Count + "; author checks: " + ([regex]::Matches($t, '\\authorcheck\{')).Count
}
