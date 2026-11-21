#!/bin/bash
# Build the files of the NEW Figshare item for revision 4 (raw records of the release-3.1 campaigns).
# Read-only on the repository and the runs; writes only to $OUT. Nothing is uploaded.
# Run on the workstation (WSL, root) after "=== QUEUE4 COMPLETE" in /opt/work/queue4.log.
#   bash ".../01_R4_borrador_(04.11.2026)/scripts/package_deposit_r4.sh"   [OUT, default below]
# The deposit is assembled outside Desktop\A on purpose (about 14 GB of raw runs before compression).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO=/opt/work/hrc31
OUT="${1:-/mnt/e/P2_deposito_figshare_R4}"
LOG="$OUT/package.log"
NICE=(nice -n 10 ionice -c2 -n7)
GIT=(git -c safe.directory="$REPO" -C "$REPO")
REPORT_TAR_SHA=fd7a039b99a8b28eb899e27c800ceb0f09de86d79fef1db26008d56b26f6784f   # FREEZE_campaign-v4-report.md
HRC_RUN_SHA=3364796a96555feb5ed6df02ed5ed15eb9f2a62de17f75150b4dcab82264573b       # idem, and manuscript Section 5.1

grep -qs "=== QUEUE4 COMPLETE" /opt/work/queue4.log || { echo "queue4 not complete"; exit 1; }
"${GIT[@]}" rev-parse -q --verify refs/tags/campaign-v4-report >/dev/null || { echo "tag campaign-v4-report missing"; exit 1; }
if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then echo "$OUT is not empty; refusing to overwrite"; exit 1; fi
mkdir -p "$OUT"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
cd "$REPO/runs"

# 1. every closed run must still match its manifest, and INDEX.csv must match MANIFEST.sha256
say "verify run directories against their manifests"
tail -n +2 INDEX.csv | while IFS=, read -r rid exp var st start cyc mh rest; do
  [ -d "$rid" ] || { echo "MISSING $rid" >> "$LOG"; continue; }
  if [ "$st" = "complete" ]; then
    got=$(sha256sum "$rid/MANIFEST.sha256" | cut -c1-64)
    [ "$got" = "$mh" ] || echo "INDEX-MISMATCH $rid" >> "$LOG"
    ( cd "$rid" && "${NICE[@]}" sha256sum --quiet -c MANIFEST.sha256 ) >> "$LOG" 2>&1 || echo "FILE-MISMATCH $rid" >> "$LOG"
  fi
done
if grep -qE "MISSING|MISMATCH" "$LOG"; then say "verification FAILED (see log); stopping"; exit 1; fi
say "verification OK"

# 2. one archive per experiment of INDEX.csv; other closed directories; interrupted runs
declare -A seen
for exp in $(tail -n +2 INDEX.csv | cut -d, -f2 | sort -u); do
  mapfile -t dirs < <(tail -n +2 INDEX.csv | awk -F, -v e="$exp" '$2==e{print $1}' | while read -r d; do [ -d "$d" ] && echo "$d"; done)
  for d in "${dirs[@]}"; do seen[$d]=1; done
  say "archive runs_${exp}.tar.gz (${#dirs[@]} runs)"
  "${NICE[@]}" tar -cf - "${dirs[@]}" | "${NICE[@]}" pigz -p 4 -6 > "$OUT/runs_${exp}.tar.gz"
done
mapfile -t interrupted < <(ls -d */ | sed 's#/##' | while read -r d; do [ -z "${seen[$d]:-}" ] && [ ! -f "$d/MANIFEST.sha256" ] && echo "$d"; done)
mapfile -t single < <(ls -d */ | sed 's#/##' | while read -r d; do [ -z "${seen[$d]:-}" ] && [ -f "$d/MANIFEST.sha256" ] && echo "$d"; done)
if [ ${#single[@]} -gt 0 ]; then
  say "archive runs_other_closed.tar.gz (${#single[@]} closed directories not in INDEX.csv: ${single[*]})"
  "${NICE[@]}" tar -cf - "${single[@]}" | "${NICE[@]}" pigz -p 4 -6 > "$OUT/runs_other_closed.tar.gz"
fi
say "archive runs_interrupted_excluded.tar.gz (${#interrupted[@]} runs: ${interrupted[*]})"
"${NICE[@]}" tar -cf - "${interrupted[@]}" | "${NICE[@]}" pigz -p 4 -6 > "$OUT/runs_interrupted_excluded.tar.gz"
cp "$HERE/scripts/deposit_r4_notes/NOTE_interrupted_runs.md" "$OUT/"
# additional runs outside the pre-registration
say "archive conformance_release31_additional.tar.gz and not_a_run_mistaken_conformance_start.tar.gz"
( cd /opt/work/hrc31_post/runs && tar -czf "$OUT/conformance_release31_additional.tar.gz" ./*_conformance_ur_rtde )
( cd /opt/work/quarantine_r4 && tar -czf "$OUT/not_a_run_mistaken_conformance_start.tar.gz" . )
cp INDEX.csv "$OUT/"
cp /opt/work/queue4.log "$OUT/queue4.log"
grep -v "not launching\|queue4 running\|lock held" /opt/work/watchdog.log > "$OUT/watchdog_launches.log" || true

# 3. per-run inventory: run, experiment, status, cycles, manifest hash, archive
{
  echo "run_id,experiment,variant,status,start_utc,cycles,manifest_sha256,archive"
  tail -n +2 INDEX.csv | awk -F, '{print $1","$2","$3","$4","$5","$6","$7",runs_"$2".tar.gz"}'
  for d in "${single[@]}"; do echo "$d,,,closed (not in INDEX.csv),,,$(sha256sum "$d/MANIFEST.sha256" | cut -c1-64),runs_other_closed.tar.gz"; done
  for d in "${interrupted[@]}"; do echo "$d,,,interrupted (excluded),,,,runs_interrupted_excluded.tar.gz"; done
} > "$OUT/INVENTORY.csv"

# 4. results and analysis outputs (top level: Figshare keeps no folders)
cp "$REPO/results/results.json" "$REPO/results/tuning_selection.json" "$REPO/results/stop_check_compare.csv" \
   "$REPO/results/stop_check_summary.txt" "$REPO/results/stop_samples_compare.csv" "$OUT/"
cp "$REPO/results/SHA256SUMS" "$OUT/SHA256SUMS_results"
cp "$HERE/data/results_extra.json" "$HERE/data/timing_miss_detail.json" "$OUT/"
cp "$HERE/numbers/r4_numbers.tex" "$OUT/manuscript_macros_r4_numbers.tex"
( cd "$HERE/scripts/../../../Vendor_docs_UR_(04.11.2026)" && tar -czf "$OUT/vendor_documents_UR.tar.gz" . )
( cd "$HERE/../../Release_3.1/freeze" && tar -czf "$OUT/freeze_records.tar.gz" . )

# 5. source at the tags, executables
say "source archives and executables"
"${GIT[@]}" archive --format=tar -o "$OUT/source_campaign-v4-report.tar" campaign-v4-report
got=$(sha256sum "$OUT/source_campaign-v4-report.tar" | cut -c1-64)
[ "$got" = "$REPORT_TAR_SHA" ] || { say "source_campaign-v4-report.tar does not reproduce the published SHA-256 (got $got); stopping"; exit 1; }
say "source_campaign-v4-report.tar reproduces the published SHA-256 ($got)"
"${GIT[@]}" archive --format=tar.gz --prefix=hrc-architecture-3.1/ -o "$OUT/source_r31-calibration.tar.gz" r31-calibration
"${GIT[@]}" show-ref --tags > "$OUT/git_tags.txt"
"${GIT[@]}" log --format='%H %cI %s' campaign-v4-report > "$OUT/git_log.txt"
got=$(sha256sum "$REPO/build/hrc_run" | cut -c1-64)
[ "$got" = "$HRC_RUN_SHA" ] || { say "build/hrc_run is not the campaign executable (got $got); stopping"; exit 1; }
( cd "$REPO/build" && tar -czf "$OUT/executables_campaign.tar.gz" hrc_run hrc_conformance hrc_protocol_bench stop_check \
  && sha256sum hrc_run hrc_conformance hrc_protocol_bench stop_check > "$OUT/executables_SHA256SUMS" )

# 6. README and checksums of the deposit itself
cp "$HERE/scripts/deposit_r4_notes/README_deposit_R4.md" "$OUT/README.md"
( cd "$OUT" && find . -type f ! -name MANIFEST_DEPOSIT.sha256 ! -name package.log -printf '%P\n' | sort \
    | xargs -d '\n' sha256sum > MANIFEST_DEPOSIT.sha256 )
say "done: $(ls "$OUT" | wc -l) entries, $(du -sh "$OUT" | cut -f1) in $OUT"
ls -la "$OUT" | tee -a "$LOG"
