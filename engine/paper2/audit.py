"""独立复核入口：不调用 core.check；基于 SQLite 编译器记录实际列读取。

注意：这是实现独立、底层引擎部分共享的交叉检查，不是 PostgreSQL 权限证明。
"""
from __future__ import annotations
import re
import sqlite3
from .core import normalize_schema, normalize_permissions, IDENT


def audit(sql: str, ddl: str, permission_record: dict, db_id: str) -> dict:
    """返回复核结论与列依赖；未知、无法编译或未授权一律不视为安全。"""
    if not isinstance(sql, str) or not re.match(r'^\s*SELECT\b', sql, re.I) or ';' in sql.rstrip().rstrip(';'):
        return {'verdict': 'unknown', 'reason': '不支持的 SQL 类型', 'reads': []}
    try:
        schema = normalize_schema(ddl)
        permissions = normalize_permissions(permission_record, db_id)
        connection = sqlite3.connect(':memory:')
        try:
            for table, columns in schema.items():
                if not re.fullmatch(IDENT, table) or not columns or any(not re.fullmatch(IDENT, c) for c in columns):
                    return {'verdict': 'unknown', 'reason': '不支持的标识符', 'reads': []}
                connection.execute('CREATE TABLE "'+table+'" ('+', '.join('"'+col+'" TEXT' for col in columns)+')')
            reads = set()
            operations = set()
            def observer(action, first, second, database, trigger):
                if action == sqlite3.SQLITE_READ:
                    reads.add((str(first).lower(), str(second).lower()))
                elif action not in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION):
                    operations.add(str(action))
                return sqlite3.SQLITE_OK
            connection.set_authorizer(observer)
            connection.execute('EXPLAIN '+sql).fetchall()
            dependencies = sorted(table+'.'+column for table, column in reads)
            if operations or not reads:
                return {'verdict':'unknown', 'reason':'存在不支持操作或无法审计读取', 'reads':dependencies}
            forbidden = sorted(table+'.'+column for table, column in reads
                               if table not in permissions or not permissions[table]
                               or (column and column not in permissions[table]))
            return {'verdict':'unsafe' if forbidden else 'safe',
                    'reason':'未授权依赖: '+', '.join(forbidden) if forbidden else '复核列依赖均已授权',
                    'reads':dependencies}
        finally:
            connection.close()
    except (sqlite3.Error, ValueError, TypeError) as error:
        return {'verdict':'unknown', 'reason':'复核无法完成: '+str(error), 'reads':[]}
