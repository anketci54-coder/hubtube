PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS observer_snapshots (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    snapshot_hash TEXT NOT NULL,
    repository_root TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    previous_snapshot_id TEXT REFERENCES observer_snapshots(id),
    UNIQUE(repository_id, snapshot_hash)
);

CREATE TABLE IF NOT EXISTS observer_files (
    snapshot_id TEXT NOT NULL REFERENCES observer_snapshots(id),
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    classification TEXT NOT NULL,
    sensitive INTEGER NOT NULL CHECK(sensitive IN (0,1)),
    PRIMARY KEY(snapshot_id, path)
);

CREATE TABLE IF NOT EXISTS observer_edges (
    snapshot_id TEXT NOT NULL REFERENCES observer_snapshots(id),
    source_path TEXT NOT NULL,
    target TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, source_path, target, edge_type)
);

CREATE TABLE IF NOT EXISTS repository_changes (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    base_snapshot_id TEXT REFERENCES observer_snapshots(id),
    new_snapshot_id TEXT NOT NULL REFERENCES observer_snapshots(id),
    path TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK(change_type IN ('ADDED','MODIFIED','DELETED')),
    change_class TEXT NOT NULL,
    old_hash TEXT,
    new_hash TEXT,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observer_snapshots_repo
ON observer_snapshots(repository_id, observed_at);

CREATE INDEX IF NOT EXISTS idx_repository_changes_snapshot
ON repository_changes(new_snapshot_id, change_class);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
