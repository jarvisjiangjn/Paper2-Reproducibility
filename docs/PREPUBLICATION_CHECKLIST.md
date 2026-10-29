# Pre-publication checklist

This checklist records issues found while preparing the supplied Paper2_V24_Local archive for public release. Do not remove an item until it has been checked against the final manuscript and source artifacts.

- [ ] **Reconcile the D3 case count.** The supplied `frozen_scenarios.jsonl` contains 88 unique records: 44 `transport` and 44 `energy`. Earlier manuscript discussions described a 44-case D3 set. Confirm which exact scenario file and subset produced the reported results; do not silently trim the source file.
- [ ] **Add the actual D3 result files.** The supplied archive contains the D3 scenario source but no D3 output JSONL, manifest, or summary.
- [ ] **Add the manual semantic-audit artifact.** The supplied archive does not contain the separate human annotation sheet for the 72 audited candidates. Publish the final annotation table and guidelines if approved for release.
- [ ] **Confirm the D1 input version.** The released D1 manifests bind to SHA-256 `0e56c06e9fd526496d25dd4d5fb5bf6e88fbe518168a844cba78140f884d7ac4` and 19,624 input records.
- [ ] **Confirm final result tables.** Recompute the manuscript's reported counts from the JSONL and execution-audit CSV after the final source version is frozen.
- [ ] **Agree on a code license with all relevant rights holders.** No `LICENSE` file is included until that decision is made. The upstream datasets retain their own license terms.
- [ ] **Check API/model reproducibility.** Record the model identifier, endpoint, experiment date, relevant settings, and any provider changes in the final reproduction notes. Never publish API credentials.
- [ ] **Confirm external-data attribution and redistribution terms.** The code repository does not include the Spider SQLite database or the Spider-ACL input JSONL; it provides source links and download instructions instead.

## Sanitization performed for this package

- Removed Python bytecode/cache directories and exploratory pilot outputs.
- Excluded `config.json` and the downloaded D1 JSONL from the public package; added `config.example.json` and a pinned dataset downloader.
- Removed the local absolute Windows path from `results/spider_preflight.json`.
- Removed the raw-result `sample`, benchmark `question`, and reference `original_sql` columns from the released `results/D1/execution_audit.csv`. The source context can be joined by `scenario_id`; execution statuses, row counts, candidate SQL, output hashes, and semantic-label placeholders are retained.
