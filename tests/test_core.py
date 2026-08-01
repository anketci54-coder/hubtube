import sqlite3
import tempfile
import unittest
from pathlib import Path

from radar.core import connect, initialize, stable_hash, transition_candidate, utc_now


ROOT = Path(__file__).resolve().parents[1]


class CoreInvariantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temp.name) / "radar.db")
        initialize(self.connection, ROOT / "schema" / "001_initial.sql")
        now = utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                ("s", "github", "o/r", stable_hash("github", "o/r"), now, now),
            )
            self.connection.execute(
                "INSERT INTO source_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("sv", "s", stable_hash("x"), stable_hash("x"), None, now, "{}"),
            )
            self.connection.execute(
                "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?)",
                ("c", "sv", "DISCOVERED", None, now, now),
            )

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_transition_is_idempotent(self):
        kwargs = dict(
            candidate_id="c", new_status="FETCHED", reason="test",
            operation_type="fetch", input_version="1", worker_version="w1"
        )
        self.assertTrue(transition_candidate(self.connection, **kwargs))
        self.assertFalse(transition_candidate(self.connection, **kwargs))
        self.assertEqual(1, self.connection.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0])

    def test_events_are_append_only(self):
        transition_candidate(
            self.connection, candidate_id="c", new_status="FETCHED", reason="test",
            operation_type="fetch", input_version="1", worker_version="w1"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("DELETE FROM candidate_events")


if __name__ == "__main__":
    unittest.main()
