"""Conservative Paper 2 prototype. SQLite compilation is a supported-dialect boundary,
not a PostgreSQL authorization proof. No SQL is executed against user data.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re
import sqlite3
from typing import Any

IDENT = r'[A-Za-z_][A-Za-z_0-9]*'
PROJECTION = re.compile(r'^\s*SELECT\s+(.+?)\s+FROM\s+('+IDENT+r')(?:\s+(?:AS\s+)?('+IDENT+r'))?\s*;?\s*$', re.I | re.S)
BARE = re.compile(r'^('+IDENT+r')(?:\.('+IDENT+r'))?$', re.I)
UNSAFE = re.compile(r'\b(?:PRAGMA|ATTACH|DETACH|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|VACUUM|EXPLAIN|WITH|RECURSIVE)\b', re.I)

@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    sql: str | None = None
    method: str | None = None
    semantic_status: str = 'not_assessed'
    original_status: str | None = None
    partial_answer_notice: str | None = None

    def json(self) -> dict[str, Any]:
        return asdict(self)


def normalize_schema(ddl: str) -> dict[str, list[str]]:
    """Extract schema through SQLite DDL compilation; refuse non-CREATE-TABLE statements."""
    statements = [x.strip() for x in ddl.split(';') if x.strip()]
    if not statements or any(not re.match(r'^CREATE\s+TABLE\s+', x, re.I) for x in statements):
        raise ValueError('unsupported DDL: only CREATE TABLE is accepted')
    con = sqlite3.connect(':memory:')
    try:
        for stmt in statements:
            con.execute(stmt)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t.lower(): [r[1].lower() for r in con.execute('PRAGMA table_info("'+t.replace('"','""')+'")')] for t in tables}
    finally:
        con.close()


def normalize_permissions(record: dict[str, Any], db_id: str) -> dict[str, set[str]]:
    """Only explicit SELECT grants; [] means NO columns, never ALL."""
    result: dict[str, set[str]] = {}
    for name, item in record.get('tables', {}).items():
        parts = name.lower().split('.')
        if len(parts) != 2 or parts[0] != db_id.lower():
            continue
        if 'SELECT' not in {str(x).upper() for x in item.get('operations', [])} and 'ALL' not in {str(x).upper() for x in item.get('operations', [])}:
            continue
        result[parts[1]] = {str(c).lower() for c in item.get('columns', [])}
    return result


def check(sql: str, ddl: str, permission_record: dict[str, Any], db_id: str) -> Decision:
    """Independent of legacy adjudicator. SQLite authorizer resolves bindings and reads.

    Refuse SQL outside SQLite-supported SELECT and SQL with unresolved identifiers.
    SQLite authorizer is an independent compiler-based check, not DB-native PostgreSQL ACL.
    """
    if not sql or not re.match(r'^\s*SELECT\b', sql, re.I) or UNSAFE.search(sql) or ';' in sql.rstrip().rstrip(';'):
        return Decision('deny', 'unsupported or non-read-only SQL')
    try:
        schema = normalize_schema(ddl)
        perms = normalize_permissions(permission_record, db_id)
        con = sqlite3.connect(':memory:')
        try:
            for table, columns in schema.items():
                if not columns or not re.fullmatch(IDENT, table) or any(not re.fullmatch(IDENT, c) for c in columns):
                    return Decision('deny', 'unsupported schema identifier')
                con.execute('CREATE TABLE "'+table+'" ('+', '.join('"'+c+'" TEXT' for c in columns)+')')
            denied: list[str] = []
            reads: list[str] = []
            def authorize(action, p1, p2, db, trigger):
                if action == sqlite3.SQLITE_READ:
                    table = str(p1).lower(); col = str(p2).lower()
                    reads.append(table+'.'+col)
                    if table not in perms or not perms[table] or (col and col not in perms[table]):
                        denied.append(table+'.'+col)
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            con.set_authorizer(authorize)
            try:
                con.execute('EXPLAIN '+sql).fetchall()
            except sqlite3.DatabaseError as exc:
                if denied:
                    return Decision('unauthorized', 'unauthorized resources: '+', '.join(sorted(set(denied))))
                return Decision('deny', 'unsupported or unresolved SQL: '+str(exc))
            if not reads:
                return Decision('deny', 'no auditable table reads')
            return Decision('permit', 'compiler-resolved reads authorized', sql)
        finally:
            con.close()
    except (sqlite3.DatabaseError, ValueError) as exc:
        return Decision('deny', 'schema failure: '+str(exc))


def projection_candidate(sql: str, ddl: str, permissions: dict[str, Any], db_id: str) -> str | None:
    """Only plain SELECT col1,col2 FROM table. No predicates, DISTINCT, joins, aggregates,
    aliases in projection, LIMIT, or implicit semantics-changing transformations.
    Candidate is a disclosed partial projection, NOT a validated semantic recovery.
    """
    match = PROJECTION.fullmatch(sql.strip())
    if not match:
        return None
    raw, table, alias = match.groups()
    if alias and alias.upper() in {'WHERE','JOIN','ORDER','GROUP','LIMIT','HAVING','UNION','OFFSET'}:
        return None
    cols = [x.strip() for x in raw.split(',')]
    if len(cols) < 2:
        return None
    try:
        schema = normalize_schema(ddl)
        perms = normalize_permissions(permissions, db_id)
    except (sqlite3.DatabaseError, ValueError):
        return None
    table = table.lower()
    if table not in schema or table not in perms:
        return None
    retained: list[str] = []
    dropped = 0
    for item in cols:
        col_match = BARE.fullmatch(item)
        if not col_match:
            return None
        prefix, suffix = col_match.groups()
        if suffix:
            if prefix.lower() not in {table, (alias or '').lower()}:
                return None
            col = suffix.lower()
        else:
            col = prefix.lower()
        if col not in schema[table]:
            return None
        if col in perms[table]:
            retained.append(item)
        else:
            dropped += 1
    if not dropped or not retained:
        return None
    return 'SELECT '+', '.join(retained)+' FROM '+table+((' AS '+alias) if alias else '')


def process(sql: str, ddl: str, permissions: dict[str, Any], db_id: str) -> Decision:
    initial = check(sql, ddl, permissions, db_id)
    if initial.status == 'permit':
        return Decision('permit', initial.reason, sql, original_status='permit')
    if initial.status != 'unauthorized':
        return Decision('deny', initial.reason, original_status=initial.status)
    candidate = projection_candidate(sql, ddl, permissions, db_id)
    if candidate is None:
        return Decision('deny', 'no supported, auditable recovery path', original_status='unauthorized')
    final = check(candidate, ddl, permissions, db_id)
    if final.status != 'permit':
        return Decision('deny', 'candidate rejected by final validator: '+final.reason, original_status='unauthorized')
    return Decision('revised_permit', 'authorized partial projection; semantic validity requires review', candidate,
                    'projection_only', 'pending_human_review', 'unauthorized',
                    '仅提供授权范围内的部分答案；原请求中的部分内容未提供。')
