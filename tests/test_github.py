from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from radar.github import GitHubScanError, extract_repository, load_repositories


class GitHubTests(unittest.TestCase):
    def test_loads_read_only_repository_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[[repositories]]\nkey="app"\ngithub="owner/repo"\nread_only=true\n', encoding="utf-8")
            self.assertEqual(load_repositories(config), [{"key": "app", "github": "owner/repo"}])

    def test_rejects_non_read_only_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[[repositories]]\nkey="app"\ngithub="owner/repo"\nread_only=false\n', encoding="utf-8")
            with self.assertRaisesRegex(GitHubScanError, "read_only=true"):
                load_repositories(config)

    def test_extracts_normal_github_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            archive = temp / "repo.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("owner-repo-abc/readme.md", "ok")
            root = extract_repository(archive, temp / "out")
            self.assertEqual((root / "readme.md").read_text(), "ok")

    def test_rejects_zip_slip_path(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            archive = temp / "repo.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("owner-repo-abc/../escape.txt", "bad")
            with self.assertRaisesRegex(GitHubScanError, "güvensiz"):
                extract_repository(archive, temp / "out")


if __name__ == "__main__":
    unittest.main()
