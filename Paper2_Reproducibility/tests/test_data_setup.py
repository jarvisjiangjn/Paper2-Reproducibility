import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.download_access_control_dataset import validate_jsonl
from scripts.install_spider_database import install_archive


class TestDatasetSetup(unittest.TestCase):
    def test_validate_jsonl_checks_schema_and_hash(self):
        record = {
            "db_id": "sample_db",
            "user": "User_1",
            "query": "SELECT id FROM items",
            "question": "List item identifiers",
            "ground_truth_label": "[]",
            "access_policy_sql": "GRANT SELECT (id) ON sample_db.items TO sample_db_User_1;",
            "schema_ddl": "CREATE TABLE items (id INTEGER);",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            count, digest = validate_jsonl(path, expected_records=1)
            self.assertEqual(count, 1)
            self.assertEqual(len(digest), 64)

    def test_installer_copies_only_database_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "spider.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("spider/database/sample_db/sample_db.sqlite", b"fake-sqlite-for-path-test")
                zipped.writestr("spider/tables.json", "[]")
                zipped.writestr("spider/train_spider.json", "[]")
            destination = root / "installed"
            result = install_archive(archive, destination)
            self.assertEqual(result["sqlite_files_copied"], 1)
            self.assertTrue((destination / "database/sample_db/sample_db.sqlite").is_file())
            self.assertTrue((destination / "tables.json").is_file())
            self.assertFalse((destination / "train_spider.json").exists())


if __name__ == "__main__":
    unittest.main()
