"""Regression tests construct fake sensitive values at runtime, never real secrets."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from check_privacy import findings, scan, scan_history


class PrivacyTests(unittest.TestCase):
    def test_addresses(self):
        for parts in [(100, 90, 80, 70), (192, 168, 10, 20), (8, 8, 4, 4)]:
            value = ".".join(map(str, parts)).encode()
            self.assertTrue(findings("README.md", value))
        ipv6 = ":".join(["fd00", "1234", "", "1"]).encode()
        self.assertTrue(findings("README.md", ipv6))
        self.assertFalse(findings("server.py", b"127.0.0.1 0.0.0.0 ::1"))

    def test_paths_credentials_and_binary(self):
        self.assertTrue(findings("README.md", ("/home/" + "someone/project").encode()))
        credential = '"' + "password" + '": ' + '"not-a-real-secret"'
        self.assertTrue(findings("config.json", credential.encode()))
        self.assertTrue(findings("settings.yaml", ("password" + ": fake-secret").encode()))
        self.assertTrue(findings("notes.md", ("API_KEY" + "=fake-secret").encode()))
        self.assertTrue(findings("README.md", ("https://user:" + "fake@example.org").encode()))
        self.assertTrue(findings("image.png", b"\x89PNG\0"))
        self.assertTrue(findings("link", b"target", "120000"))
        self.assertFalse(findings("config.example", b'api_key: "${PROVIDER_KEY}"'))

    def test_private_files_are_rejected_even_without_secret_patterns(self):
        for name in [
            "data/report.md",
            ".env",
            ".env.local",
            "backup.sqlite3",
            "auth.json",
            "journal/test-results/screen.png",
        ]:
            self.assertTrue(findings(name, b"ordinary content"), name)
        self.assertFalse(findings(".env.example", b"JOURNAL_PORT=8097"))

    def test_scans_index_not_unstaged_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            file = root / "notes.md"
            file.write_text("Address: " + ".".join(map(str, [100, 90, 80, 70])))
            subprocess.run(["git", "add", "notes.md"], cwd=root, check=True)
            file.write_text("Safe unstaged replacement")
            self.assertTrue(scan(root)[1])
            self.assertFalse(scan(root, worktree=True)[1])

    def test_history_catches_information_removed_later(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for contents in [".".join(map(str, [100, 90, 80, 70])), "Safe replacement"]:
                (root / "notes.md").write_text(contents)
                subprocess.run(["git", "add", "notes.md"], cwd=root, check=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=Fixture",
                        "-c",
                        "user.email=fixture@example.org",
                        "-c",
                        "commit.gpgsign=false",
                        "commit",
                        "-qm",
                        "Synthetic fixture",
                    ],
                    cwd=root,
                    check=True,
                )
            self.assertFalse(scan(root)[1])
            self.assertTrue(scan_history(root)[1])


if __name__ == "__main__":
    unittest.main()
