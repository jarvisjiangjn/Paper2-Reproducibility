"""Check that every database referenced by the D1 corpus has a readable SQLite file."""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spider", default=str(ROOT / "data" / "spider"))
    parser.add_argument("--source", default=str(ROOT / "data" / "access_control_dataset.jsonl"))
    args = parser.parse_args()

    spider_root = pathlib.Path(args.spider)
    source_path = pathlib.Path(args.source)
    from verify_sqlite import locate

    database_ids = collections.Counter()
    with source_path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                database_ids[json.loads(line)["db_id"]] += 1

    found = []
    missing = []
    invalid = []
    for database_id in sorted(database_ids):
        database_path = locate(spider_root, database_id)
        if database_path is None:
            missing.append(database_id)
            continue
        try:
            uri = database_path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
            found.append(database_id)
        except sqlite3.Error as error:
            invalid.append({"db_id": database_id, "error": str(error)})

    summary = {
        "corpus_databases": len(database_ids),
        "matched_sqlite": len(found),
        "missing_count": len(missing),
        "missing": missing,
        "invalid": invalid,
        "example_expected": "data/spider/database/<db_id>/<db_id>.sqlite",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    output = ROOT / "results" / "spider_preflight.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
