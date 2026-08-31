from __future__ import annotations

import json
import os
import tempfile
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .observer import observe_repository, persist_snapshot


API_ROOT = "https://api.github.com"


class GitHubScanError(RuntimeError):
    pass


def load_repositories(config_path: Path) -> list[dict[str, str]]:
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GitHubScanError(f"Yapılandırma okunamadı: {exc}") from exc
    repositories = config.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise GitHubScanError("Yapılandırmada en az bir [[repositories]] kaydı gerekli")
    result: list[dict[str, str]] = []
    for index, item in enumerate(repositories, start=1):
        if not isinstance(item, dict):
            raise GitHubScanError(f"repositories[{index}] geçerli bir tablo değil")
        key = item.get("key")
        full_name = item.get("github")
        if not isinstance(key, str) or not key.strip():
            raise GitHubScanError(f"repositories[{index}].key eksik")
        if (not isinstance(full_name, str) or full_name.count("/") != 1
                or any(not part.strip() for part in full_name.split("/"))):
            raise GitHubScanError(f"repositories[{index}].github OWNER/REPO biçiminde olmalı")
        if item.get("read_only") is not True:
            raise GitHubScanError(f"{key}: read_only=true zorunludur")
        result.append({"key": key.strip(), "github": full_name.strip()})
    return result


def _request(url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "HubTube-Radar/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("RADAR_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def download_repository(full_name: str, destination: Path) -> None:
    try:
        with urllib.request.urlopen(_request(f"{API_ROOT}/repos/{full_name}"), timeout=30) as response:
            metadata = json.load(response)
        default_branch = metadata.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch:
            raise GitHubScanError(f"Varsayılan branch bulunamadı: {full_name}")
        archive_url = f"https://github.com/{full_name}/archive/refs/heads/{default_branch}.zip"
        with urllib.request.urlopen(_request(archive_url), timeout=60) as response:
            destination.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        messages = {
            401: "GitHub kimlik doğrulaması başarısız",
            403: "GitHub erişimi reddetti veya API kotası doldu",
            404: f"Repository bulunamadı: {full_name}",
        }
        raise GitHubScanError(messages.get(exc.code, f"GitHub HTTP {exc.code} döndürdü")) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise GitHubScanError(f"GitHub bağlantısı başarısız: {exc}") from exc


def extract_repository(archive: Path, destination: Path) -> Path:
    try:
        with zipfile.ZipFile(archive) as bundle:
            files = [item for item in bundle.infolist() if not item.is_dir()]
            if not files:
                raise GitHubScanError("GitHub arşivi boş")
            roots = {PurePosixPath(item.filename).parts[0] for item in files}
            if len(roots) != 1:
                raise GitHubScanError("GitHub arşivinde beklenmeyen kök yapısı")
            root = next(iter(roots))
            for item in files:
                parts = PurePosixPath(item.filename).parts
                if not parts or parts[0] != root or ".." in parts:
                    raise GitHubScanError("GitHub arşivinde güvensiz dosya yolu")
                target = destination.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
    except zipfile.BadZipFile as exc:
        raise GitHubScanError("GitHub geçersiz bir ZIP arşivi döndürdü") from exc
    return destination / root


def scan_github(connection, config_path: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for repository in load_repositories(config_path):
        with tempfile.TemporaryDirectory(prefix="hubtube-") as directory:
            temp = Path(directory)
            archive = temp / "repository.zip"
            download_repository(repository["github"], archive)
            snapshot = observe_repository(extract_repository(archive, temp / "source"))
            persisted = persist_snapshot(connection, repo_key=repository["key"],
                                         full_name=repository["github"], snapshot=snapshot)
            results.append({
                "repo_key": repository["key"], "full_name": repository["github"],
                "file_count": snapshot["file_count"], "snapshot_hash": snapshot["snapshot_hash"],
                "changed": persisted["changed"], "changes": len(persisted["changes"]),
                "impacted_context": len(persisted["impacted_context"]),
            })
    return results
