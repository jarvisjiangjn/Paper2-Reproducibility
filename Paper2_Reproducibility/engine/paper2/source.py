"""Adapter for the Spider access-control JSONL source and its explicit GRANTs."""
import re

GRANT = re.compile(r"GRANT\s+SELECT\s*\(([^)]*)\)\s+ON\s+([\w]+)\.([\w]+)\s+TO\s+([\w]+)\s*;", re.I)


def permissions(row):
    """Extract explicit column-level SELECT grants for the record's current user."""
    db, user = row["db_id"], row["user"]
    role = db + "_" + user
    tables = {}
    for columns, schema, table, grantee in GRANT.findall(row["access_policy_sql"]):
        if schema.lower() != db.lower() or grantee.lower() != role.lower():
            continue
        name = schema + "." + table
        item = tables.setdefault(name, {"operations": ["SELECT"], "columns": []})
        item["columns"] = sorted(
            set(item["columns"]) | {column.strip().lower() for column in columns.split(",") if column.strip()}
        )
    return {"db_id": db, "user": user, "tables": tables}
