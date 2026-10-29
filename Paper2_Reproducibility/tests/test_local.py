import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verify_sqlite import execute, locate  # noqa: E402


class TestLocal(unittest.TestCase):
    def test_read_only_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "sample.sqlite"
            with sqlite3.connect(db) as connection:
                connection.execute("CREATE TABLE items(id INTEGER)")
                connection.execute("INSERT INTO items VALUES (3)")

            default_result = execute(db, "SELECT id FROM items")
            self.assertEqual(default_result["status"], "executed")
            self.assertEqual(default_result["sample"], [])

            sampled_result = execute(
                db, "SELECT id FROM items", include_samples=True
            )
            self.assertEqual(sampled_result["sample"], [[repr(3)]])

            rejected_result = execute(db, "DELETE FROM items")
            self.assertEqual(rejected_result["status"], "rejected_non_select")
            with sqlite3.connect(db) as connection:
                count = connection.execute(
                    "SELECT count(*) FROM items"
                ).fetchone()[0]
            self.assertEqual(count, 1)

    def test_locate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            db = root / "database" / "academic" / "academic.sqlite"
            db.parent.mkdir(parents=True)
            db.touch()

            self.assertEqual(locate(root, "academic"), db)
            self.assertIsNone(locate(root, "../etc"))


if __name__ == "__main__":
    unittest.main()
