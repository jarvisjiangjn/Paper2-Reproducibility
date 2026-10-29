"""Unified D1 benchmark and D3 frozen-scenario experiment runner.

Offline methods and preflight checks do not call an LLM. Model-based methods
require the explicit --enable-api flag and PAPER2_API_KEY/PAPER2_API_KEYS.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "engine"))

from paper2.core import check  # noqa: E402
from paper2.source import permissions  # noqa: E402
from postgen import METHODS, api_settings, run_one  # noqa: E402


MODEL_METHODS = {"naive_retry", "sql_aware_retry", "diagnostic_revision"}


def source_rows(path: pathlib.Path):
    """Adapt Spider-ACL records to the common query-policy record format."""
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            yield {
                "scenario_id": f"D1_{line_number:06d}",
                "db_id": record["db_id"],
                "question": record["question"],
                "original_sql": record["query"],
                "schema_ddl": record["schema_ddl"],
                "permissions": permissions(record),
                "origin": "external_reference_sql",
            }


def scenario_rows(path: pathlib.Path):
    """Read frozen D3 scenarios without modifying or filtering their source rows."""
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            required = ("scenario_id", "db_id", "question", "original_sql", "schema_ddl", "permissions")
            missing = [key for key in required if key not in row]
            if missing:
                raise ValueError(f"Missing fields in {path}, line {line_number}: {missing}")
            yield row


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def existing_result_ids(path: pathlib.Path) -> set[str]:
    """Read the IDs already written for resume; reject duplicate cache records."""
    seen: set[str] = set()
    if not path.exists():
        return seen
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            scenario_id = record["scenario_id"]
            if scenario_id in seen:
                raise RuntimeError(f"Duplicate result ID in {path}: {scenario_id}")
            seen.add(scenario_id)
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("D1", "D3"), required=True)
    parser.add_argument("--source", help="Override the default input path")
    parser.add_argument("--out", default="unified_results")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=["deny_only", "rule"])
    parser.add_argument("--max-cases", type=int, default=0, help="0 means process the full input")
    parser.add_argument("--preflight", action="store_true", help="Check initial SQL without writing results")
    parser.add_argument("--enable-api", action="store_true", help="Explicitly allow model API calls")
    parser.add_argument(
        "--eligible-only",
        action="store_true",
        help="Exploratory triage: skip model calls for unauthorized queries with no authorized columns",
    )
    args = parser.parse_args()

    default_source = BASE / "frozen_scenarios.jsonl" if args.dataset == "D3" else BASE / "data/access_control_dataset.jsonl"
    source = pathlib.Path(args.source) if args.source else default_source
    if not source.exists():
        parser.error(f"Missing source: {source}")

    input_sha256 = sha256_file(source)
    selected_model_methods = set(args.methods) & MODEL_METHODS
    if selected_model_methods and not (args.enable_api or args.preflight):
        parser.error("Model methods require --enable-api")

    api = (
        api_settings(json.loads((BASE / "config.json").read_text(encoding="utf-8")))
        if selected_model_methods and args.enable_api and not args.preflight
        else None
    )

    output_dir = pathlib.Path(args.out) / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "protocol": "unified_v1",
        "dataset": args.dataset,
        "input_sha256": input_sha256,
        "methods": args.methods,
        "max_cases": args.max_cases,
        "eligible_only": args.eligible_only,
        "model": api["model"] if api else None,
        "base_url": api["base_url"] if api else None,
        "policy": "All outputs rechecked by compiler gate and independent audit; semantic fidelity not certified",
    }
    manifest_path = output_dir / "manifest.json"
    if not args.preflight:
        if manifest_path.exists():
            current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if current_manifest != manifest:
                raise RuntimeError("Manifest mismatch; use a new output directory rather than mixing runs")
        else:
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    iterator = source_rows(source) if args.dataset == "D1" else scenario_rows(source)
    initial_status = collections.Counter()
    processed = 0
    sinks = {}
    seen_by_method = {}

    if not args.preflight:
        for method in args.methods:
            result_path = output_dir / f"{method}.jsonl"
            seen = existing_result_ids(result_path)
            seen_by_method[method] = seen
            sinks[method] = result_path.open("a", encoding="utf-8")

    try:
        for row in iterator:
            if args.max_cases and processed >= args.max_cases:
                break
            processed += 1
            initial = check(row["original_sql"], row["schema_ddl"], row["permissions"], row["db_id"])
            initial_status[initial.status] += 1
            if args.preflight:
                continue

            skip_model_calls = False
            if args.eligible_only and initial.status == "unauthorized":
                from paper2.core import normalize_permissions

                has_authorized_columns = any(
                    normalize_permissions(row["permissions"], row["db_id"]).values()
                )
                if not has_authorized_columns:
                    initial_status["triaged_no_authorized_columns"] += 1
                    skip_model_calls = True

            for method in args.methods:
                if row["scenario_id"] in seen_by_method[method]:
                    continue
                if skip_model_calls and method in MODEL_METHODS:
                    result = {
                        "scenario_id": row["scenario_id"],
                        "method": method,
                        "initial_status": initial.status,
                        "decision": "not_attempted",
                        "reason": "triaged_no_authorized_columns",
                        "api_calls": 0,
                        "semantic_status": "not_assessed",
                    }
                else:
                    result = run_one(row, method, api=api)
                sinks[method].write(json.dumps(result, ensure_ascii=False) + "\n")
                sinks[method].flush()
                seen_by_method[method].add(row["scenario_id"])

            if processed % 1000 == 0:
                print(f"Processed {processed}: {dict(initial_status)}", flush=True)
    finally:
        for sink in sinks.values():
            sink.close()

    summary = {
        "dataset": args.dataset,
        "input_sha256": input_sha256,
        "processed": processed,
        "initial_status": dict(initial_status),
        "methods": {},
        "note": "Model call outcomes and authorization acceptance do not prove semantic recovery",
    }

    if not args.preflight:
        for method in args.methods:
            path = output_dir / f"{method}.jsonl"
            with path.open(encoding="utf-8") as stream:
                records = [json.loads(line) for line in stream if line.strip()]
            summary["methods"][method] = {
                "records": len(records),
                "decisions": dict(collections.Counter(record["decision"] for record in records)),
                "api_calls": sum(record.get("api_calls", 0) for record in records),
                "api_errors": sum(bool(record.get("api_error")) for record in records),
            }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
