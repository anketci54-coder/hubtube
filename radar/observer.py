from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from .core import stable_hash, utc_now


SKIP_DIRECTORIES = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache",
    "node_modules", ".venv", "venv", "work",
}
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
TEST_MARKERS = {"test", "tests", "spec", "specs"}
CONFIG_NAMES = {
    "cargo.toml", "cargo.lock", "pyproject.toml", "requirements.txt",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", ".github",
}


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    sha256: str
    classification: str
    sensitive: bool


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    edge_type: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sensitive(relative: Path) -> bool:
    lowered = relative.name.lower()
    return lowered in SENSITIVE_NAMES or relative.suffix.lower() in SENSITIVE_SUFFIXES


def _classify(relative: Path) -> str:
    lowered_parts = {part.lower() for part in relative.parts}
    lowered_name = relative.name.lower()
    if _is_sensitive(relative):
        return "sensitive"
    if lowered_parts & TEST_MARKERS or lowered_name.startswith("test_") or lowered_name.endswith("_test.py"):
        return "test"
    if lowered_name in CONFIG_NAMES or ".github" in lowered_parts:
        return "configuration"
    if relative.suffix.lower() in {".md", ".rst", ".txt"}:
        return "documentation"
    return "source"


def _python_imports(path: Path, relative: Path) -> list[Edge]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
    except (UnicodeDecodeError, SyntaxError, OSError):
        return []
    edges: list[Edge] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            edges.append(Edge(relative.as_posix(), name, "import"))
    return edges


def observe_repository(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Repository path is not a directory: {root}")

    files: list[FileRecord] = []
    edges: list[Edge] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        if not path.is_file():
            continue
        record = FileRecord(
            path=relative.as_posix(),
            size=path.stat().st_size,
            sha256=_sha256(path),
            classification=_classify(relative),
            sensitive=_is_sensitive(relative),
        )
        files.append(record)
        if path.suffix.lower() == ".py" and not record.sensitive:
            edges.extend(_python_imports(path, relative))

    snapshot_material = "\n".join(f"{item.path}\0{item.sha256}" for item in files)
    snapshot_hash = hashlib.sha256(snapshot_material.encode("utf-8")).hexdigest()
    counts: dict[str, int] = {}
    for item in files:
        counts[item.classification] = counts.get(item.classification, 0) + 1
    return {
        "schema_version": 1,
        "repository_root": str(root),
        "snapshot_hash": snapshot_hash,
        "file_count": len(files),
        "classification_counts": counts,
        "files": [asdict(item) for item in files],
        "edges": [asdict(edge) for edge in edges],
    }


def _change_class(path: str, classification: str) -> str:
    name = Path(path).name.lower()
    if classification == "documentation":
        return "documentation"
    if classification == "sensitive":
        return "security"
    if name in {"cargo.lock", "package-lock.json", "pnpm-lock.yaml", "requirements.txt"}:
        return "dependency"
    if "license" in name:
        return "license"
    if classification == "configuration":
        return "configuration"
    if classification == "test":
        return "test"
    return "capability"


def persist_snapshot(
    connection: sqlite3.Connection,
    *,
    repo_key: str,
    full_name: str,
    snapshot: dict[str, object],
) -> dict[str, object]:
    repository_id = stable_hash("repository", repo_key)
    snapshot_id = stable_hash(repository_id, str(snapshot["snapshot_hash"]))
    now = utc_now()
    previous = connection.execute(
        """SELECT id FROM observer_snapshots
           WHERE repository_id = ? ORDER BY observed_at DESC, id DESC LIMIT 1""",
        (repository_id,),
    ).fetchone()
    previous_id = previous["id"] if previous else None
    existing = connection.execute(
        "SELECT id FROM observer_snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    if existing:
        return {"snapshot_id": snapshot_id, "changed": False, "changes": [], "impacted_context": []}

    with connection:
        connection.execute(
            """INSERT OR IGNORE INTO repositories
               (id, repo_key, provider, native_id, full_name, read_only, created_at)
               VALUES (?, ?, 'github', NULL, ?, 1, ?)""",
            (repository_id, repo_key, full_name, now),
        )
        connection.execute(
            """INSERT INTO observer_snapshots
               (id, repository_id, snapshot_hash, repository_root, observed_at, file_count, previous_snapshot_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                repository_id,
                snapshot["snapshot_hash"],
                snapshot["repository_root"],
                now,
                snapshot["file_count"],
                previous_id,
            ),
        )
        connection.executemany(
            """INSERT INTO observer_files
               (snapshot_id, path, size, content_hash, classification, sensitive)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id, item["path"], item["size"], item["sha256"],
                    item["classification"], int(item["sensitive"]),
                )
                for item in snapshot["files"]
            ],
        )
        connection.executemany(
            """INSERT INTO observer_edges (snapshot_id, source_path, target, edge_type)
               VALUES (?, ?, ?, ?)""",
            [(snapshot_id, edge["source"], edge["target"], edge["edge_type"]) for edge in snapshot["edges"]],
        )

        changes = _calculate_changes(connection, previous_id, snapshot_id)
        connection.executemany(
            """INSERT INTO repository_changes
               (id, repository_id, base_snapshot_id, new_snapshot_id, path, change_type,
                change_class, old_hash, new_hash, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    stable_hash(snapshot_id, change["path"], change["change_type"]),
                    repository_id, previous_id, snapshot_id, change["path"],
                    change["change_type"], change["change_class"],
                    change["old_hash"], change["new_hash"], now,
                )
                for change in changes
            ],
        )

    impacted = _impacted_context(connection, snapshot_id, {item["path"] for item in changes})
    return {
        "snapshot_id": snapshot_id,
        "previous_snapshot_id": previous_id,
        "changed": bool(changes),
        "changes": changes,
        "impacted_context": impacted,
    }


def _calculate_changes(
    connection: sqlite3.Connection, previous_id: str | None, snapshot_id: str
) -> list[dict[str, object]]:
    current_rows = connection.execute(
        "SELECT path, content_hash, classification FROM observer_files WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchall()
    current = {row["path"]: row for row in current_rows}
    previous: dict[str, sqlite3.Row] = {}
    if previous_id:
        rows = connection.execute(
            "SELECT path, content_hash, classification FROM observer_files WHERE snapshot_id = ?",
            (previous_id,),
        ).fetchall()
        previous = {row["path"]: row for row in rows}
    changes: list[dict[str, object]] = []
    for path in sorted(set(previous) | set(current)):
        old, new = previous.get(path), current.get(path)
        if old is None:
            change_type = "ADDED"
        elif new is None:
            change_type = "DELETED"
        elif old["content_hash"] != new["content_hash"]:
            change_type = "MODIFIED"
        else:
            continue
        classification = (new or old)["classification"]
        changes.append({
            "path": path,
            "change_type": change_type,
            "change_class": _change_class(path, classification),
            "old_hash": old["content_hash"] if old else None,
            "new_hash": new["content_hash"] if new else None,
        })
    return changes


def _impacted_context(
    connection: sqlite3.Connection, snapshot_id: str, changed_paths: set[str]
) -> list[dict[str, str]]:
    impacted: list[dict[str, str]] = []
    for path in sorted(changed_paths):
        impacted.append({"path": path, "reason": "changed"})
    rows = connection.execute(
        "SELECT source_path, target, edge_type FROM observer_edges WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchall()
    module_names = {Path(path).with_suffix("").as_posix().replace("/", "."): path for path in changed_paths}
    for row in rows:
        if row["target"] in module_names and row["source_path"] not in changed_paths:
            impacted.append({"path": row["source_path"], "reason": f"{row['edge_type']}:{module_names[row['target']]}"})
    return impacted


def write_snapshot(snapshot: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
