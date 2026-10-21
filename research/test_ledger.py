import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ledger import archive, identity, progress, recent


class LedgerTests(unittest.TestCase):
    def test_progress_is_bounded_resets_and_validates_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(65):
                progress(root, "reading", f"Source {i}", "https://example.org/paper")
            events = json.loads((root / "progress.json").read_text())
            self.assertEqual(len(events), 60)
            self.assertEqual(events[-1]["message"], "Source 64")
            for url in ("javascript:alert(1)", ":".join(["https", "//user", "secret@example.org"])):
                with self.assertRaises(ValueError):
                    progress(root, "reading", "Unsafe", url)
            progress(root, "starting", "New run")
            self.assertEqual(len(json.loads((root / "progress.json").read_text())), 1)

    def test_identifiers_ignore_versions_and_tracking(self):
        item = {"title": "Paper", "url": "https://example.org/paper?utm_source=rss#abstract"}
        self.assertEqual(identity(item), "https://example.org/paper")
        self.assertEqual(identity(dict(item, doi="https://doi.org/10.1234/ABC")), "doi:10.1234/abc")
        self.assertEqual(identity(dict(item, arxiv_id="2610.12345v2")), "arxiv:2610.12345")

    def test_retries_are_idempotent_and_updates_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = [{"title": "Paper", "url": "https://example.org/paper"}]
            first = archive(root, "# Briefing\nOriginal finding", items)
            Path(first["path"]).unlink()  # Retry repairs a missing export.
            self.assertEqual(archive(root, "# Briefing\nOriginal finding", items), first)
            self.assertTrue(Path(first["path"]).exists())
            archive(root, "# Briefing\nSubstantive follow-up", items)
            self.assertEqual(len(recent(root, 30)), 2)
            with sqlite3.connect(root / "coverage.sqlite3") as db:
                self.assertEqual(db.execute("SELECT count(*) FROM reports").fetchone()[0], 2)
            self.assertEqual(first["status"], "archived_locally")

    def test_invalid_batch_does_not_commit_partial_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                archive(
                    root,
                    "report",
                    [
                        {"title": "Good", "url": "https://example.org"},
                        {"title": "Bad", "url": "file:///etc/passwd"},
                    ],
                )
            self.assertEqual(recent(root, 30), [])

    def test_quiet_day_can_be_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = archive(Path(tmp), "No significant updates; sources checked.", [])
            self.assertTrue(Path(result["path"]).exists())


if __name__ == "__main__":
    unittest.main()
