"""Install Spider SQLite databases from a locally downloaded official Spider ZIP.

Only SQLite database files and tables.json are copied. The rest of the archive is
not extracted. No third-party packages are required.
"""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "data" / "spider"
DB_ID = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")


def install_archive(archive_path: Path, destination: Path = DEFAULT_DEST, overwrite: bool = False) -> dict:
    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Spider ZIP not found: {archive_path}")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    copied = 0
    copied_tables = False
    with tempfile.TemporaryDirectory(prefix="paper2_spider_extract_") as temp_dir:
        stage = Path(temp_dir)
        with zipfile.ZipFile(archive_path) as zipped:
            for info in zipped.infolist():
                if info.is_dir():
                    continue
                parts = PurePosixPath(info.filename).parts
                basename = parts[-1] if parts else ""
                if basename == "tables.json":
                    target = stage / "tables.json"
                    with zipped.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    copied_tables = True
                    continue
                if not basename.lower().endswith(".sqlite"):
                    continue

                if "database" in parts:
                    index = parts.index("database")
                    tail = parts[index:]
                    if len(tail) < 3:
                        continue
                    db_id = tail[-2]
                    filename = tail[-1]
                elif len(parts) >= 2:
                    db_id, filename = parts[-2], parts[-1]
                    tail = ("database", db_id, filename)
                else:
                    continue

                if not DB_ID.fullmatch(db_id) or filename != f"{db_id}.sqlite":
                    continue
                target = stage / "database" / db_id / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                copied += 1

        if copied == 0:
            raise ValueError(
                "No Spider database files matching database/<db_id>/<db_id>.sqlite were found. "
                "Check that the selected ZIP is the official Spider 1.0 archive."
            )
        if not overwrite:
            existing = list((destination / "database").glob("*/*.sqlite"))
            if existing:
                raise FileExistsError(
                    f"{len(existing)} database files already exist under {destination / 'database'}. "
                    "Use --overwrite to replace them."
                )
        staged_database = stage / "database"
        target_database = destination / "database"
        if target_database.exists():
            shutil.rmtree(target_database)
        shutil.copytree(staged_database, target_database)
        if copied_tables:
            shutil.copy2(stage / "tables.json", destination / "tables.json")

    result = {
        "archive": str(archive_path),
        "destination": str(destination.resolve()),
        "sqlite_files_copied": copied,
        "tables_json_copied": copied_tables,
        "expected_layout": str(destination / "database" / "<db_id>" / "<db_id>.sqlite"),
    }
    print(f"Installed {copied} SQLite database files into {destination / 'database'}")
    if not copied_tables:
        print("Note: tables.json was not found in the archive; execution auditing may still work.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="Path to the downloaded Spider ZIP")
    parser.add_argument("--destination", default=str(DEFAULT_DEST))
    parser.add_argument("--overwrite", action="store_true", help="Replace existing database files")
    args = parser.parse_args()
    install_archive(Path(args.archive), Path(args.destination), args.overwrite)


if __name__ == "__main__":
    main()
