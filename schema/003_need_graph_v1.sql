PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS need_change_proposals (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    snapshot_id TEXT NOT NULL REFERENCES observer_snapshots(id),
    need_key TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('ADD_OR_UPDATE','RAISE_PRIORITY','LOWER_PRIORITY','ARCHIVE')),
    proposed_priority TEXT NOT NULL CHECK(proposed_priority IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    problem TEXT NOT NULL,
    critical INTEGER NOT NULL CHECK(critical IN (0,1)),
    rule_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    approval_status TEXT NOT NULL CHECK(approval_status IN ('PENDING','APPROVED','REJECTED')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(repository_id, snapshot_id, need_key, rule_id)
);

CREATE INDEX IF NOT EXISTS idx_need_proposals_review
ON need_change_proposals(repository_id, approval_status, created_at);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (3, strftime('%Y-%m-%dT%H:%M:%fZ','now'));

