from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .core import stable_hash, utc_now


@dataclass(frozen=True)
class NeedSuggestion:
    need_key: str
    priority: str
    problem: str
    rule_id: str
    evidence: list[dict[str, object]]
    critical: bool = False


def _latest_snapshot(connection: sqlite3.Connection, repository_id: str) -> sqlite3.Row:
    row = connection.execute(
        """SELECT id, snapshot_hash, observed_at FROM observer_snapshots
           WHERE repository_id = ? ORDER BY observed_at DESC, id DESC LIMIT 1""",
        (repository_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Repository has no observer snapshot")
    return row


def _derive_suggestions(
    connection: sqlite3.Connection, snapshot: sqlite3.Row
) -> list[NeedSuggestion]:
    counts = {
        row["classification"]: row["count"]
        for row in connection.execute(
            """SELECT classification, COUNT(*) AS count FROM observer_files
               WHERE snapshot_id = ? GROUP BY classification""",
            (snapshot["id"],),
        ).fetchall()
    }
    files = {
        row["path"]
        for row in connection.execute(
            "SELECT path FROM observer_files WHERE snapshot_id = ?", (snapshot["id"],)
        ).fetchall()
    }
    suggestions: list[NeedSuggestion] = []
    sensitive_count = counts.get("sensitive", 0)
    if sensitive_count:
        suggestions.append(NeedSuggestion(
            need_key="security.sensitive-file-boundary",
            priority="CRITICAL",
            problem="Repository contains sensitive-path material that requires strict analysis boundaries.",
            rule_id="sensitive-files-present-v1",
            evidence=[{"snapshot_id": snapshot["id"], "sensitive_file_count": sensitive_count}],
            critical=True,
        ))

    dependency_files = sorted(files & {
        "Cargo.lock", "requirements.txt", "package-lock.json", "pnpm-lock.yaml", "poetry.lock",
    })
    if dependency_files:
        suggestions.append(NeedSuggestion(
            need_key="dependency.health-monitoring",
            priority="HIGH",
            problem="Locked or declared dependencies require license, maintenance, and vulnerability monitoring.",
            rule_id="dependency-manifest-present-v1",
            evidence=[{"snapshot_id": snapshot["id"], "paths": dependency_files}],
        ))

    source_count = counts.get("source", 0)
    test_count = counts.get("test", 0)
    if source_count and test_count == 0:
        suggestions.append(NeedSuggestion(
            need_key="quality.test-coverage",
            priority="HIGH",
            problem="Source files exist but no test files were detected.",
            rule_id="no-tests-detected-v1",
            evidence=[{"snapshot_id": snapshot["id"], "source_count": source_count, "test_count": 0}],
        ))
    elif source_count and test_count / source_count < 0.20:
        suggestions.append(NeedSuggestion(
            need_key="quality.test-coverage",
            priority="MEDIUM",
            problem="Detected test-to-source ratio is below the initial deterministic review threshold.",
            rule_id="low-test-ratio-v1",
            evidence=[{
                "snapshot_id": snapshot["id"], "source_count": source_count,
                "test_count": test_count, "ratio": round(test_count / source_count, 4),
            }],
        ))

    change_counts = {
        row["change_class"]: row["count"]
        for row in connection.execute(
            """SELECT change_class, COUNT(*) AS count FROM repository_changes
               WHERE new_snapshot_id = ? GROUP BY change_class""",
            (snapshot["id"],),
        ).fetchall()
    }
    has_previous_snapshot = connection.execute(
        "SELECT previous_snapshot_id FROM observer_snapshots WHERE id = ?", (snapshot["id"],)
    ).fetchone()["previous_snapshot_id"] is not None
    for change_class, need_key, priority, problem in (
        ("security", "security.active-change-review", "CRITICAL", "Recent changes affect a security-classified boundary."),
        ("dependency", "dependency.change-review", "HIGH", "Recent dependency changes require compatibility and supply-chain review."),
        ("license", "license.change-review", "CRITICAL", "Recent license changes require an immediate policy-gate review."),
    ):
        if has_previous_snapshot and change_counts.get(change_class, 0):
            suggestions.append(NeedSuggestion(
                need_key=need_key,
                priority=priority,
                problem=problem,
                rule_id=f"recent-{change_class}-change-v1",
                evidence=[{
                    "snapshot_id": snapshot["id"],
                    "change_class": change_class,
                    "change_count": change_counts[change_class],
                }],
                critical=priority == "CRITICAL",
            ))
    return suggestions


def propose_needs(connection: sqlite3.Connection, repo_key: str) -> list[dict[str, object]]:
    repository = connection.execute(
        "SELECT id FROM repositories WHERE repo_key = ?", (repo_key,)
    ).fetchone()
    if repository is None:
        raise ValueError(f"Unknown repository: {repo_key}")
    snapshot = _latest_snapshot(connection, repository["id"])
    suggestions = _derive_suggestions(connection, snapshot)
    created: list[dict[str, object]] = []
    now = utc_now()
    with connection:
        for suggestion in suggestions:
            evidence_json = json.dumps(suggestion.evidence, sort_keys=True, separators=(",", ":"))
            proposal_id = stable_hash(
                repository["id"], suggestion.need_key, suggestion.rule_id,
                snapshot["snapshot_hash"], evidence_json,
            )
            connection.execute(
                """INSERT OR IGNORE INTO need_change_proposals
                   (id, repository_id, snapshot_id, need_key, action, proposed_priority,
                    problem, critical, rule_id, evidence_json, approval_status, created_at)
                   VALUES (?, ?, ?, ?, 'ADD_OR_UPDATE', ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (
                    proposal_id, repository["id"], snapshot["id"], suggestion.need_key,
                    suggestion.priority, suggestion.problem, int(suggestion.critical),
                    suggestion.rule_id, evidence_json, now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM need_change_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            created.append(dict(row))
    return created


def approve_need_proposal(
    connection: sqlite3.Connection, proposal_id: str, approved_by: str
) -> dict[str, object]:
    proposal = connection.execute(
        "SELECT * FROM need_change_proposals WHERE id = ?", (proposal_id,)
    ).fetchone()
    if proposal is None:
        raise ValueError(f"Unknown proposal: {proposal_id}")
    if proposal["approval_status"] == "REJECTED":
        raise ValueError("Rejected proposal cannot be approved")
    if proposal["approval_status"] == "APPROVED":
        existing = connection.execute(
            """SELECT n.id, n.need_key, n.current_version, n.critical, v.priority, v.status
               FROM needs n JOIN need_versions v
                 ON v.need_id = n.id AND v.version = n.current_version
               WHERE n.repository_id = ? AND n.need_key = ?""",
            (proposal["repository_id"], proposal["need_key"]),
        ).fetchone()
        if existing is None:
            raise RuntimeError("Approved proposal has no materialized need")
        return {
            "need_id": existing["id"], "need_key": existing["need_key"],
            "version": existing["current_version"], "priority": existing["priority"],
            "critical": bool(existing["critical"]), "status": existing["status"],
        }
    now = utc_now()
    need_id = stable_hash(proposal["repository_id"], proposal["need_key"])
    current = connection.execute(
        "SELECT current_version, critical FROM needs WHERE id = ?", (need_id,)
    ).fetchone()
    next_version = (current["current_version"] + 1) if current else 1
    critical = max(int(proposal["critical"]), int(current["critical"]) if current else 0)
    with connection:
        if current:
            connection.execute(
                "UPDATE needs SET current_version = ?, critical = ? WHERE id = ?",
                (next_version, critical, need_id),
            )
        else:
            connection.execute(
                """INSERT INTO needs (id, repository_id, need_key, critical, current_version)
                   VALUES (?, ?, ?, ?, ?)""",
                (need_id, proposal["repository_id"], proposal["need_key"], critical, next_version),
            )
        connection.execute(
            """INSERT INTO need_versions
               (need_id, version, status, priority, problem, evidence_json, approved_by, created_at)
               VALUES (?, ?, 'ACTIVE', ?, ?, ?, ?, ?)""",
            (
                need_id, next_version, proposal["proposed_priority"], proposal["problem"],
                proposal["evidence_json"], approved_by, now,
            ),
        )
        connection.execute(
            """UPDATE need_change_proposals
               SET approval_status = 'APPROVED', reviewed_by = ?, reviewed_at = ? WHERE id = ?""",
            (approved_by, now, proposal_id),
        )
    return {
        "need_id": need_id,
        "need_key": proposal["need_key"],
        "version": next_version,
        "priority": proposal["proposed_priority"],
        "critical": bool(critical),
        "status": "ACTIVE",
    }


def list_needs(connection: sqlite3.Connection, repo_key: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """SELECT n.id, n.need_key, n.critical, n.current_version, v.status,
                  v.priority, v.problem, v.evidence_json, v.approved_by, v.created_at
           FROM needs n JOIN repositories r ON r.id = n.repository_id
           JOIN need_versions v ON v.need_id = n.id AND v.version = n.current_version
           WHERE r.repo_key = ? ORDER BY v.priority DESC, n.need_key""",
        (repo_key,),
    ).fetchall()
    return [dict(row) for row in rows]
