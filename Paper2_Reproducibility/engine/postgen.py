"""Bounded SQL revision protocol used by ``run_unified.py``.

The model proposes candidates. Deterministic authorization and dependency checks
make the final decision. Semantic sufficiency is not certified by this module.
"""
from __future__ import annotations

import json
import os
import time

from api_client import APIStop, request_sql
from paper2.audit import audit
from paper2.core import check, normalize_permissions, normalize_schema, projection_candidate

METHODS = ("deny_only", "rule", "naive_retry", "sql_aware_retry", "diagnostic_revision")
VERSION = "postgen_v1"


def api_settings(config: dict) -> dict:
    """Read model settings and credentials without storing secrets in the config file."""
    settings = dict(config.get("models", {}).get("recovery", {}))
    raw_keys = os.environ.get("PAPER2_API_KEYS", "") or os.environ.get("PAPER2_API_KEY", "")
    settings["keys"] = [key.strip() for key in raw_keys.split(",") if key.strip()]
    if not settings["keys"] or not settings.get("model") or settings["model"].startswith("REPLACE_"):
        raise ValueError("Set PAPER2_API_KEY and configure models.recovery.model in config.json")
    return settings


def diagnose(row: dict):
    """Run the initial authorization check and record observed SQL dependencies."""
    first = check(row["original_sql"], row["schema_ddl"], row["permissions"], row["db_id"])
    evidence = audit(row["original_sql"], row["schema_ddl"], row["permissions"], row["db_id"])
    return first, evidence


def authorized_ddl(row: dict) -> str:
    """Expose only explicitly authorized columns in the schema sent to the model."""
    schema = normalize_schema(row["schema_ddl"])
    permissions = normalize_permissions(row["permissions"], row["db_id"])
    statements = []
    for table, columns in sorted(schema.items()):
        allowed = [column for column in columns if column in permissions.get(table, set())]
        if allowed:
            definitions = ", ".join(f"{column} TEXT" for column in allowed)
            statements.append(f"CREATE TABLE {table} ({definitions});")
    return "\n".join(statements)


def prompt_for(row: dict, first, evidence: dict, method: str) -> tuple[str, str]:
    """Build the method-specific prompt and its authorization-filtered schema."""
    ddl = authorized_ddl(row)
    if method == "naive_retry":
        question = (
            "User question: " + row["question"] +
            "\nGenerate one useful authorized SELECT query using only the provided schema. "
            "If no meaningful answer can be provided, output DENY. Do not explain."
        )
    elif method == "sql_aware_retry":
        question = (
            "User question: " + row["question"] + "\nOriginal SQL: " + row["original_sql"] +
            "\nGenerate one useful authorized SELECT query based on the original SQL and the provided authorized schema. "
            "Do not invent relationships or change the queried population. If no meaningful answer is possible, "
            "output DENY. Only output SQL or DENY."
        )
    else:
        question = (
            "User question: " + row["question"] + "\nOriginal SQL: " + row["original_sql"] +
            "\nDeterministic authorization diagnosis: " + first.reason +
            "\nObserved SQL column dependencies: " + json.dumps(evidence.get("reads", [])) +
            "\nRevise the original SQL minimally to preserve a useful authorized part of the request. "
            "Never invent table equivalences, infer protected values, or drop a predicate that changes the selected population. "
            "If no meaningful authorized query is possible, output DENY. Only output SQL or DENY."
        )
    return question, ddl


def run_one(row: dict, method: str, api: dict | None = None, client=None) -> dict:
    """Evaluate one query-policy record using one of the five released methods."""
    started = time.perf_counter()
    first, evidence = diagnose(row)
    candidate = None
    cause = ""
    api_error = None
    calls = 0

    if first.status == "permit":
        candidate = row["original_sql"]
        cause = "original_permitted"
    elif first.status != "unauthorized":
        cause = "unsupported_or_invalid_initial_sql"
    elif method == "deny_only":
        cause = "deny_only"
    elif method == "rule":
        candidate = projection_candidate(
            row["original_sql"], row["schema_ddl"], row["permissions"], row["db_id"]
        )
        cause = "safe_projection_rule" if candidate else "rule_not_applicable"
    elif method in ("naive_retry", "sql_aware_retry", "diagnostic_revision"):
        question, ddl = prompt_for(row, first, evidence, method)
        if not ddl:
            cause = "no_authorized_schema"
        else:
            calls = 1
            try:
                if client:
                    result = client(question, ddl)
                else:
                    result = request_sql(
                        question, ddl, api["model"], api["base_url"], api["keys"], 0,
                        api.get("timeout", 240), api.get("retries", 4),
                    )
                candidate = None if result.strip().upper() == "DENY" else result.strip()
                cause = "model_candidate" if candidate else "model_declined"
            except APIStop:
                raise
            except Exception as exc:  # retain the failure in the per-record output
                api_error = type(exc).__name__ + ": " + str(exc)
                cause = "api_error"
    else:
        raise ValueError(f"Unsupported method: {method}")

    final = check(candidate, row["schema_ddl"], row["permissions"], row["db_id"]) if candidate else None
    final_audit = audit(candidate, row["schema_ddl"], row["permissions"], row["db_id"]) if candidate else None
    safe = bool(final and final.status == "permit" and final_audit["verdict"] == "safe")
    if candidate and not safe:
        cause = "final_adjudication_rejected"

    decision = "permit" if safe and first.status == "permit" else "revised_permit" if safe else "deny"
    return {
        "scenario_id": row["scenario_id"],
        "scenario_type": row.get("scenario_type"),
        "method": method,
        "initial_status": first.status,
        "initial_reason": first.reason,
        "initial_reads": evidence.get("reads", []),
        "initial_audit": evidence["verdict"],
        "decision": decision,
        "candidate_sql": candidate if safe else None,
        "rejected_candidate_sql": candidate if candidate and not safe else None,
        "final_reason": final.reason if final else None,
        "final_audit": final_audit["verdict"] if final_audit else None,
        "reason": cause,
        "api_calls": calls,
        "api_error": api_error,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "semantic_status": "not_independently_verified",
        "partial_answer_notice": (
            "Partial answer may omit requested information" if decision == "revised_permit" else None
        ),
    }
