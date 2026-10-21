"""Worker safety checks without invoking Hermes, Docker, or a model."""

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "worker", Path(__file__).with_name("journal-worker.py")
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = patch.object(worker, "HOME_DIR", self.root)
        self.home.start()
        worker.STATE.clear()
        worker.STATE.update(busy=False, stage="ready", last_error=None)

    def tearDown(self):
        self.home.stop()
        self.tmp.cleanup()

    def test_missing_execution_database_is_idle(self):
        self.assertFalse(worker.active())

    def test_unreadable_execution_database_is_not_idle(self):
        (self.root / "cron").mkdir()
        (self.root / "cron" / "executions.db").write_text("not sqlite")
        self.assertTrue(worker.active())

    def test_only_our_active_job_blocks_execution(self):
        (self.root / "cron").mkdir()
        with sqlite3.connect(self.root / "cron" / "executions.db") as db:
            db.execute("CREATE TABLE executions (job_id TEXT, status TEXT)")
            db.execute("INSERT INTO executions VALUES ('ours', 'running')")
        with patch.object(worker, "job", return_value={"id": "ours"}):
            self.assertTrue(worker.active())
        with patch.object(worker, "job", return_value={"id": "other"}):
            self.assertFalse(worker.active())

    def test_cli_success_without_archive_does_not_report_publication(self):
        with (
            patch.object(worker, "cli"),
            self.assertRaisesRegex(RuntimeError, "without a new archived"),
        ):
            worker.run_briefing()
        self.assertNotIn("last_completed", worker.STATE)

    def test_publication_requires_new_archive(self):
        with patch.object(worker, "cli"), patch.object(worker, "archive_count", side_effect=[1, 2]):
            worker.run_briefing()
        self.assertGreater(worker.STATE["last_completed"], 0)

    def test_topic_jobs_pin_profiles_and_ledger_paths_and_respect_pauses(self):
        catalog = [
            {"id": "default", "name": "Journal", "enabled": True},
            {"id": "sports", "name": "Sports", "enabled": False},
        ]
        with patch.object(worker, "cli") as cli, patch.object(worker, "job", return_value={}):
            worker.configure_jobs({"enabled": True, "time": "09:15"}, catalog)
        calls = [call.args for call in cli.call_args_list]
        self.assertIn(("resume", "morning-research"), calls)
        self.assertIn(("pause", "morning-research-sports"), calls)
        create = next(c for c in calls if c[0] == "create" and "morning-research-sports" in c)
        root = self.root / "research/topics/sports"
        self.assertIn(f"Read {root}/profile.json", create[2])
        self.assertIn(f"ledger.py --root {root} recent", create[2])
        self.assertIn(f"ledger.py --root {root} archive --report {root}/draft.md", create[2])
        self.assertNotIn("/opt/data/research", create[2])

    def test_another_topics_archive_cannot_complete_manual_run(self):
        (self.root / "research").mkdir()
        with sqlite3.connect(self.root / "research/coverage.sqlite3") as db:
            db.execute("CREATE TABLE reports (id TEXT)")
            db.execute("INSERT INTO reports VALUES ('legacy')")
        with (
            patch.object(worker, "cli") as cli,
            self.assertRaisesRegex(RuntimeError, "without a new archived"),
        ):
            worker.run_briefing("sports")
        cli.assert_called_once_with("run", "morning-research-sports")

    def test_active_topic_job_blocks_manual_dispatch(self):
        (self.root / "cron").mkdir()
        with sqlite3.connect(self.root / "cron/executions.db") as db:
            db.execute("CREATE TABLE executions (job_id TEXT, status TEXT)")
            db.execute("INSERT INTO executions VALUES ('sports-job', 'running')")
        with (
            patch.object(worker, "topics", return_value=[{"id": "default"}, {"id": "sports"}]),
            patch.object(
                worker,
                "job",
                side_effect=lambda name: {
                    "id": "sports-job" if name.endswith("sports") else "legacy"
                },
            ),
        ):
            self.assertTrue(worker.active())

    def test_each_topic_has_its_own_cadence_time_and_pause_state(self):
        catalog = [
            {
                "id": "default",
                "enabled": True,
                "schedule": {"enabled": True, "time": "08:00", "cadence": "weekly", "weekday": 1},
            },
            {
                "id": "agents",
                "enabled": True,
                "schedule": {"enabled": True, "time": "09:30", "cadence": "daily"},
            },
            {
                "id": "work",
                "enabled": True,
                "schedule": {"enabled": False, "time": "10:15", "cadence": "weekdays"},
            },
        ]
        with (
            patch.object(worker, "cli") as cli,
            patch.object(worker, "job", return_value={"id": "exists"}),
        ):
            worker.configure_jobs({"enabled": False, "time": "07:00"}, catalog)
        calls = [call.args for call in cli.call_args_list]
        edits = {c[1]: c[3] for c in calls if c[0] == "edit"}
        self.assertEqual(
            edits,
            {
                "morning-research": "0 8 * * 1",
                "morning-research-agents": "30 9 * * *",
                "morning-research-work": "15 10 * * 1-5",
            },
        )
        self.assertIn(("resume", "morning-research"), calls)
        self.assertIn(("resume", "morning-research-agents"), calls)
        self.assertIn(("pause", "morning-research-work"), calls)

    def test_weekly_days_and_legacy_daily_cron(self):
        self.assertEqual(worker.cron_expression({"time": "08:00"}), "0 8 * * *")
        for day in range(7):
            self.assertEqual(
                worker.cron_expression({"time": "23:59", "cadence": "weekly", "weekday": day}),
                f"59 23 * * {day}",
            )
        for changes in ({"weekday": True}, {"weekday": 7}, {"cadence": "monthly"}):
            with self.assertRaises(ValueError):
                worker.cron_expression({"time": "08:00", **changes})


if __name__ == "__main__":
    unittest.main()
