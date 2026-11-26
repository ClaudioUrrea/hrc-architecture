# Correction notice for the earlier deposits

This notice applies to releases 1.0.0–2.1.0 of this repository and to versions 1.0.0–2.1.0 of
Figshare item 10.6084/m9.figshare.33194013. It replaces the provenance paragraphs that described
some of their files as "recorded values".

---

**Correction of data provenance (12 October 2026).** The data files in versions 1.0.0 to 2.1.0
of this deposit are **not experimental records**. The original logs and the implementation
source code of the study described in manuscript electronics-4587969 (MDPI *Electronics*) were
lost, and no backup exists. The deposited datasets — including those previously described as
"recorded values" (`faults_450.csv`, `interfailure.csv`, `plc_runs.csv`, `effort_log.csv`,
`conformance_log.csv`, `cloc_lizard.json`) as well as the files described as "reference
reconstructions" — were generated or re-derived to be consistent with the summary statistics
printed in the manuscript. They therefore cannot be used to verify the results of that
manuscript, and they should not be used as evidence for them. The analysis scripts in these
versions recompute the printed numbers from those generated files; this shows internal
consistency only.

The repository also did not contain the C++ implementation (vendor adapters, real-time layer,
protocol servers) described in the manuscript's Data Availability Statement.

The author has informed the journal. The implementation is being rebuilt
(github.com/ClaudioUrrea/hrc-architecture, release 3.x) and the experiments will be repeated
with raw logs deposited as written by the software, with SHA-256 manifests. Any future
publication will report only results from those new runs. Earlier versions of this item remain
retrievable under their version DOIs so that the history is auditable.
