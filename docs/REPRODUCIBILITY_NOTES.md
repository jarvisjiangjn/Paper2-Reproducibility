# Reproducibility Notes

## D1 input and results

The D1 result manifests identify the input dataset by SHA-256 `0e56c06e9fd526496d25dd4d5fb5bf6e88fbe518168a844cba78140f884d7ac4` and record 19,624 input records. Confirm that the downloaded input matches this version before comparing newly generated results with the results committed in this repository.

The repository includes offline baseline outputs, LLM-revision result files, manifests, summaries, and a SQLite execution-audit CSV for D1. The released execution-audit CSV omits raw result-row samples and duplicated benchmark question/reference SQL text. Original context can be joined to the audit records by `scenario_id` using the corresponding dataset.

## D3 scenario set and results

`frozen_scenarios.jsonl` contains 88 records: 44 transport scenarios and 44 energy scenarios. The repository does not currently include D3 output JSONL files, a D3 manifest or summary, or the separate manual semantic-audit spreadsheet for the 72 audited candidates. Before reporting D3 results, verify the scenario count and exact scenario subset against the manuscript and retain the corresponding audit version. Do not infer missing results or labels from the scenario source alone.

## Interpretation

- D1 uses benchmark reference SQL as the initial proposal; it does not measure the failure rate of deployed Text-to-SQL agents.
- Authorization acceptance, successful SQL execution, and semantic sufficiency are separate outcomes. Successful execution alone does not establish semantic equivalence.
- The authorization gate relies on SQLite compilation and authorizer behavior for the supported SQL subset; it is not a PostgreSQL-native authorization proof.
- D3 uses frozen synthetic scenarios and should be reported separately from D1 benchmark results.

## Data and code licensing

The repository provides scripts and instructions for obtaining the external datasets rather than including the downloaded Spider databases or the D1 access-control JSONL. Cite the source datasets and follow their applicable terms when using or redistributing data. No license file is currently provided for this repository's own code; contributors should agree on a license before redistributing it as open-source software.
