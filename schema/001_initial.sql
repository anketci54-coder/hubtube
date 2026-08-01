PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    repo_key TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL CHECK (provider = 'github'),
    native_id TEXT,
    full_name TEXT NOT NULL UNIQUE,
    read_only INTEGER NOT NULL DEFAULT 1 CHECK (read_only = 1),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repository_snapshots (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    commit_sha TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    UNIQUE(repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS repository_files (
    snapshot_id TEXT NOT NULL REFERENCES repository_snapshots(id),
    path TEXT NOT NULL,
    content_hash TEXT,
    classification TEXT NOT NULL DEFAULT 'source',
    sensitive INTEGER NOT NULL DEFAULT 0 CHECK (sensitive IN (0,1)),
    PRIMARY KEY(snapshot_id, path)
);

CREATE TABLE IF NOT EXISTS repository_impact_edges (
    snapshot_id TEXT NOT NULL REFERENCES repository_snapshots(id),
    from_path TEXT NOT NULL,
    to_path TEXT NOT NULL,
    edge_type TEXT NOT NULL CHECK(edge_type IN ('import','dependency','test','config','security_boundary','data_model')),
    PRIMARY KEY(snapshot_id, from_path, to_path, edge_type)
);

CREATE TABLE IF NOT EXISTS needs (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    need_key TEXT NOT NULL,
    critical INTEGER NOT NULL DEFAULT 0 CHECK(critical IN (0,1)),
    current_version INTEGER NOT NULL,
    UNIQUE(repository_id, need_key)
);

CREATE TABLE IF NOT EXISTS need_versions (
    need_id TEXT NOT NULL REFERENCES needs(id),
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PROPOSED','ACTIVE','SATISFIED','STALE','ARCHIVED')),
    priority TEXT NOT NULL CHECK(priority IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    problem TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(need_id, version)
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    native_id TEXT NOT NULL,
    source_key TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(provider, native_id)
);

CREATE TABLE IF NOT EXISTS source_versions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    content_key TEXT NOT NULL,
    normalized_hash TEXT NOT NULL,
    last_modified_at TEXT,
    fetched_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(source_id, content_key)
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id),
    current_status TEXT NOT NULL CHECK(current_status IN (
        'DISCOVERED','FETCH_PENDING','FETCHED','NORMALIZED','DEDUPLICATED',
        'PREFILTERED','ENRICHMENT_PENDING','ENRICHED','ANALYSIS_PENDING',
        'ANALYZED','MEASUREMENT_PENDING','MEASURED','REVIEW_REQUIRED',
        'BLOCKED','REPORTED','RETRYABLE_ERROR','TERMINAL_ERROR')),
    deferred_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    previous_status TEXT,
    current_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    worker_version TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS candidate_events_no_update
BEFORE UPDATE ON candidate_events
BEGIN
    SELECT RAISE(ABORT, 'candidate_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS candidate_events_no_delete
BEFORE DELETE ON candidate_events
BEGIN
    SELECT RAISE(ABORT, 'candidate_events is append-only');
END;

CREATE TABLE IF NOT EXISTS idempotency_records (
    job_key TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    operation_type TEXT NOT NULL,
    input_version TEXT NOT NULL,
    worker_version TEXT NOT NULL,
    result_ref TEXT,
    succeeded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_gate_results (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    gate_order INTEGER NOT NULL CHECK(gate_order BETWEEN 1 AND 6),
    gate_type TEXT NOT NULL,
    result TEXT NOT NULL CHECK(result IN ('PASS','BLOCK','DEFER','NOT_EVALUATED')),
    reason TEXT NOT NULL,
    input_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    UNIQUE(candidate_id, gate_type, input_version, policy_version)
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    evidence_type TEXT NOT NULL,
    provenance TEXT NOT NULL,
    material INTEGER NOT NULL CHECK(material IN (0,1)),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    dimension TEXT NOT NULL CHECK(dimension IN ('speed','capability','security','economy','repository_fit')),
    impact_score INTEGER CHECK(impact_score BETWEEN 0 AND 100),
    confidence_score INTEGER CHECK(confidence_score BETWEEN 0 AND 100),
    evidence_level TEXT NOT NULL,
    applicability TEXT NOT NULL CHECK(applicability IN ('confirmed','probable','uncertain','not_applicable')),
    formula_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_evidence_ids_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    UNIQUE(candidate_id, repository_id, dimension, formula_id, policy_version)
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    decision TEXT NOT NULL CHECK(decision IN ('IGNORE','WATCH','INVESTIGATE','URGENT_INVESTIGATION')),
    reasons_json TEXT NOT NULL,
    need_profile_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_checkpoints (
    source_name TEXT PRIMARY KEY,
    last_successful_cursor TEXT,
    last_successful_at TEXT,
    next_scan_from TEXT,
    overlap_hours INTEGER NOT NULL CHECK(overlap_hours >= 0),
    status TEXT NOT NULL CHECK(status IN ('HEALTHY','PARTIAL','PAUSED','ERROR')),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','SUCCESS','PARTIAL_SUCCESS','FAILED')),
    discovered INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    changed INTEGER NOT NULL DEFAULT 0,
    skipped_unchanged INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    deferred_budget INTEGER NOT NULL DEFAULT 0,
    checkpoint_advanced INTEGER NOT NULL DEFAULT 0 CHECK(checkpoint_advanced IN (0,1))
);

CREATE TABLE IF NOT EXISTS user_feedback (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    repository_id TEXT NOT NULL REFERENCES repositories(id),
    verdict TEXT NOT NULL CHECK(verdict IN ('VERY_USEFUL','USEFUL','IRRELEVANT','ALREADY_EXISTS','TOO_EXPENSIVE','UNSAFE','LATER')),
    human_useful INTEGER NOT NULL CHECK(human_useful IN (0,1)),
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidate_events_candidate ON candidate_events(candidate_id, id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(current_status);
CREATE INDEX IF NOT EXISTS idx_source_versions_source ON source_versions(source_id, fetched_at);
CREATE INDEX IF NOT EXISTS idx_assessments_candidate_repo ON assessments(candidate_id, repository_id);
CREATE INDEX IF NOT EXISTS idx_decisions_date ON decisions(decided_at);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));

