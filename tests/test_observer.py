import tempfile
import unittest
from pathlib import Path

from radar.observer import observe_repository


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


if __name__ == "__main__":
    unittest.main()
