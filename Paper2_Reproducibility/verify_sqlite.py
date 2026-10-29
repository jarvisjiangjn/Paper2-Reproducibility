"""Post-hoc SQLite execution checks; execution success is not a semantic-success oracle."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))

from paper2.audit import audit  # noqa: E402
from paper2.core import check  # noqa: E402
from paper2.source import permissions  # noqa: E402


DB_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")


def locate(root: pathlib.Path, db_id: str) -> pathlib.Path | None:
    """Find a Spider SQLite file without allowing path traversal through db_id."""
    if not DB_ID_PATTERN.fullmatch(db_id):
        return None
    candidates = (
        root / db_id / f"{db_id}.sqlite",
        root / "database" / db_id / f"{db_id}.sqlite",
    )
    return next((path for path in candidates if path.is_file()), None)


def execute(
    database: pathlib.Path,
    sql: str,
    limit_steps: int = 2_000_000,
    max_rows: int = 2_000,
    include_samples: bool = False,
) -> dict:
    """Execute one SELECT using a read-only SQLite connection and resource limits."""
    if not re.match(r"^\s*SELECT\b", sql or "", re.IGNORECASE):
        return {"status": "rejected_non_select"}

    uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=3)
    steps = [0]

    def progress() -> int:
        steps[0] += 1000
        return 1 if steps[0] > limit_steps else 0

    try:
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(progress, 1000)
        cursor = connection.execute(sql)
        row_count = 0
        digest = hashlib.sha256()
        samples = []

        while True:
            batch = cursor.fetchmany(100)
            if not batch:
                break
            for row in batch:
                row_count += 1
                if include_samples and row_count <= 3:
                    samples.append([repr(value)[:100] for value in row])
                if row_count <= max_rows:
                    serialized = json.dumps([repr(value) for value in row], ensure_ascii=False) + "\n"
                    digest.update(serialized.encode("utf-8"))
                if row_count > max_rows:
                    break
            if row_count > max_rows:
                break

        return {
            "status": "executed" if row_count <= max_rows else "row_limit",
            "rows_seen": row_count,
            "output_sha256": digest.hexdigest() if row_count <= max_rows else None,
            "sample": samples,
            "note": "SQL executed; output agreement/semantic correctness NOT established",
        }
    except sqlite3.Error as error:
        return {"status": "execution_error", "error": str(error)[:400]}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(ROOT / "data" / "access_control_dataset.jsonl"))
    parser.add_argument("--results", default=str(ROOT / "results" / "D1"))
    parser.add_argument("--spider", default=str(ROOT / "data" / "spider"))
    parser.add_argument("--out", default=str(ROOT / "results" / "D1" / "execution_audit.csv"))
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument(
        "--include-context",
        action="store_true",
        help="Include the benchmark question and reference SQL in the CSV; these can also be joined by scenario_id",
    )
    parser.add_argument(
        "--include-samples",
        action="store_true",
        help="Include up to three raw result rows per query; avoid publishing this output",
    )
    args = parser.parse_args()

    source_path = pathlib.Path(args.source)
    result_dir = pathlib.Path(args.results)
    spider_root = pathlib.Path(args.spider)
    with source_path.open(encoding="utf-8") as stream:
        source_rows = [json.loads(line) for line in stream if line.strip()]
    rows_by_id = {f"D1_{index:06d}": row for index, row in enumerate(source_rows, 1)}

    outputs = []
    stats = collections.Counter()
    for result_path in sorted(result_dir.glob("*.jsonl")):
        with result_path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                result = json.loads(line)
                if result.get("decision") not in ("permit", "revised_permit"):
                    continue
                source = rows_by_id.get(result["scenario_id"])
                sql = result.get("candidate_sql")
                if source is None or not sql:
                    continue

                database = locate(spider_root, source["db_id"])
                gate = check(sql, source["schema_ddl"], permissions(source), source["db_id"])
                dependency_audit = audit(sql, source["schema_ddl"], permissions(source), source["db_id"])
                safe = gate.status == "permit" and dependency_audit["verdict"] == "safe"
                if safe and database:
                    outcome = execute(database, sql, include_samples=args.include_samples)
                else:
                    outcome = {"status": "missing_db" if safe else "gate_rejected"}

                entry = {
                    "scenario_id": result["scenario_id"],
                    "method": result["method"],
                    "db_id": source["db_id"],
                    "candidate_sql": sql,
                    "gate_status": gate.status,
                    "audit_verdict": dependency_audit["verdict"],
                    "db_present": bool(database),
                    "execution_status": outcome["status"],
                    "rows_seen": outcome.get("rows_seen"),
                    "output_sha256": outcome.get("output_sha256"),
                    "error": outcome.get("error", ""),
                    "semantic_label": "NOT_REVIEWED",
                }
                if args.include_context:
                    entry["question"] = source["question"]
                    entry["original_sql"] = source["query"]
                if args.include_samples:
                    entry["sample"] = json.dumps(outcome.get("sample", []), ensure_ascii=False)
                outputs.append(entry)
                stats[(result["method"], outcome["status"])] += 1

                if args.max_cases and len(outputs) >= args.max_cases:
                    break
        if args.max_cases and len(outputs) >= args.max_cases:
            break

    output_path = pathlib.Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario_id", "method", "db_id", "candidate_sql", "gate_status", "audit_verdict",
        "db_present", "execution_status", "rows_seen", "output_sha256", "error", "semantic_label",
    ]
    if args.include_context:
        fieldnames[3:3] = ["question", "original_sql"]
    if args.include_samples:
        fieldnames.insert(fieldnames.index("error"), "sample")
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(outputs)

    summary = {
        "review_rows": len(outputs),
        "by_method_and_execution": {str(key): value for key, value in stats.items()},
        "output": str(output_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
