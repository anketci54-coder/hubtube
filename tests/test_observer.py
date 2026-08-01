import tempfile
import unittest
from pathlib import Path

from radar.core import connect, initialize
from radar.observer import observe_repository, persist_snapshot


ROOT = Path(__file__).resolve().parents[1]


class ObserverTests(unittest.TestCase):
    def test_observes_files_and_marks_sensitive_without_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("import json\n", encoding="utf-8")
            (root / "test_app.py").write_text("from app import main\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret-value\n", encoding="utf-8")
            snapshot = observe_repository(root)

        self.assertEqual(3, snapshot["file_count"])
        records = {item["path"]: item for item in snapshot["files"]}
        self.assertTrue(records[".env"]["sensitive"])
        self.assertEqual("test", records["test_app.py"]["classification"])
        self.assertNotIn("secret-value", str(snapshot))
        self.assertTrue(any(edge["target"] == "json" for edge in snapshot["edges"]))

    def test_snapshot_hash_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            first = observe_repository(root)["snapshot_hash"]
            second = observe_repository(root)["snapshot_hash"]
        self.assertEqual(first, second)

    def test_persists_and_diffs_incremental_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = connect(root / "radar.db")
            initialize(db, ROOT / "schema")
            source = root / "repo"
            source.mkdir()
            (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            first = persist_snapshot(
                db, repo_key="demo", full_name="owner/demo", snapshot=observe_repository(source)
            )
            self.assertTrue(first["changed"])

            unchanged = persist_snapshot(
                db, repo_key="demo", full_name="owner/demo", snapshot=observe_repository(source)
            )
            self.assertFalse(unchanged["changed"])

            (source / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            (source / "test_app.py").write_text("import app\n", encoding="utf-8")
            second = persist_snapshot(
                db, repo_key="demo", full_name="owner/demo", snapshot=observe_repository(source)
            )
            kinds = {(item["path"], item["change_type"]) for item in second["changes"]}
            self.assertIn(("app.py", "MODIFIED"), kinds)
            self.assertIn(("test_app.py", "ADDED"), kinds)
            impacted = {item["path"] for item in second["impacted_context"]}
            self.assertIn("test_app.py", impacted)
            db.close()


if __name__ == "__main__":
    unittest.main()
