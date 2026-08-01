import tempfile
import unittest
from pathlib import Path

from radar.core import connect, initialize
from radar.needs import approve_need_proposal, list_needs, propose_needs
from radar.observer import observe_repository, persist_snapshot


ROOT = Path(__file__).resolve().parents[1]


class NeedGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.connection = connect(root / "radar.db")
        initialize(self.connection, ROOT / "schema")
        self.repo = root / "repo"
        self.repo.mkdir()

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _observe(self):
        persist_snapshot(
            self.connection,
            repo_key="demo",
            full_name="owner/demo",
            snapshot=observe_repository(self.repo),
        )

    def test_proposal_requires_human_approval(self):
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._observe()
        proposals = propose_needs(self.connection, "demo")
        proposal = next(item for item in proposals if item["need_key"] == "quality.test-coverage")
        self.assertEqual([], list_needs(self.connection, "demo"))

        activated = approve_need_proposal(self.connection, proposal["id"], "reviewer")
        self.assertEqual("ACTIVE", activated["status"])
        self.assertEqual("reviewer", list_needs(self.connection, "demo")[0]["approved_by"])
        repeated = approve_need_proposal(self.connection, proposal["id"], "reviewer")
        self.assertEqual(activated["version"], repeated["version"])

    def test_critical_security_need_cannot_be_downgraded_by_new_proposal(self):
        (self.repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._observe()
        proposals = propose_needs(self.connection, "demo")
        security = next(item for item in proposals if item["need_key"] == "security.sensitive-file-boundary")
        activated = approve_need_proposal(self.connection, security["id"], "reviewer")
        self.assertTrue(activated["critical"])
        self.assertEqual("CRITICAL", activated["priority"])

    def test_proposals_are_idempotent_for_same_snapshot(self):
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._observe()
        first = propose_needs(self.connection, "demo")
        second = propose_needs(self.connection, "demo")
        self.assertEqual([item["id"] for item in first], [item["id"] for item in second])


if __name__ == "__main__":
    unittest.main()
