from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


SKIP_DIRECTORIES = {".git", ".hg", ".svn", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}
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


def write_snapshot(snapshot: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

