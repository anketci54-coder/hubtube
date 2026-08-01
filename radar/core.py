from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def stable_hash(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection, schema_path: Path) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))


def transition_candidate(
    connection: sqlite3.Connection,
    *,
    candidate_id: str,
    new_status: str,
    reason: str,
    operation_type: str,
    input_version: str,
    worker_version: str,
    result_ref: str | None = None,
) -> bool:
    """Atomically append an event, materialize state, and record idempotency.

    Returns False when the successful job result already exists.
    """
    job_key = stable_hash(candidate_id, operation_type, input_version, worker_version)
    now = utc_now()
    with connection:
        existing = connection.execute(
            "SELECT 1 FROM idempotency_records WHERE job_key = ?", (job_key,)
        ).fetchone()
        if existing:
            return False
        row = connection.execute(
            "SELECT current_status FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown candidate: {candidate_id}")
        previous_status = row["current_status"]
        connection.execute(
            """INSERT INTO candidate_events
               (candidate_id, previous_status, current_status, reason, worker_version, occurred_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (candidate_id, previous_status, new_status, reason, worker_version, now),
        )
        connection.execute(
            "UPDATE candidates SET current_status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, candidate_id),
        )
        connection.execute(
            """INSERT INTO idempotency_records
               (job_key, candidate_id, operation_type, input_version, worker_version, result_ref, succeeded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_key, candidate_id, operation_type, input_version, worker_version, result_ref, now),
        )
    return True

