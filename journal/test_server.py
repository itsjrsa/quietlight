import http.client
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class JournalTests(unittest.TestCase):
    def test_progress_is_topic_scoped_and_excludes_previous_runs(self):
        now = time.time()
        (server.CONTROL / "topics.json").write_text(
            json.dumps(
                [
                    {"id": "default", "name": "Journal", "enabled": True},
                    {"id": "another", "name": "Another", "enabled": True},
                ]
            )
        )
        (server.CONTROL / "worker.json").write_text(
            json.dumps(
                {
                    "heartbeat": now,
                    "busy": True,
                    "active_topics": {"default": now - 10},
                }
            )
        )
        (server.ROOT / "progress.json").write_text(
            json.dumps(
                [
                    {"at": now - 100, "stage": "reading", "message": "Old source"},
                    {
                        "at": now,
                        "stage": "reading",
                        "message": "Current source",
                        "url": "https://example.org",
                    },
                ]
            )
        )
        code, value, _ = self.request("/api/status?topic=default")
        self.assertEqual(code, 200)
        self.assertTrue(value["research"]["active"])
        self.assertEqual([e["message"] for e in value["research"]["events"]], ["Current source"])
        self.assertFalse(server.status("another")["research"]["active"])
        self.assertEqual(server.status("another")["research"]["events"], [])
        self.assertEqual(self.request("/api/status?topic=unknown")[0], 404)
        (server.CONTROL / "worker.json").write_text(
            json.dumps(
                {
                    "heartbeat": now - 100,
                    "busy": True,
                    "active_topics": {"default": now - 10},
                }
            )
        )
        self.assertFalse(server.status()["research"]["active"])
        (server.CONTROL / "request.json").write_text(json.dumps({"topic": "another"}))
        self.assertTrue(server.status("another")["research"]["queued"])
        self.assertFalse(server.status()["research"]["queued"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.ROOT = Path(self.tmp.name)
        server.CONTROL = server.ROOT / "journal"
        server.SESSIONS.clear()
        server.ATTEMPTS.clear()
        server.initialize()
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, body=None, origin=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.http.server_port)
        headers = {"Cookie": self.cookie}
        if host is not None:
            headers["Host"] = host
        if origin:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(
            "GET" if body is None else "POST",
            path,
            None if body is None else json.dumps(body),
            headers,
        )
        response = conn.getresponse()
        value = json.loads(response.read())
        cookie = response.getheader("Set-Cookie")
        conn.close()
        return response.status, value, cookie

    def login(self):
        code, _, cookie = self.request(
            "/api/login", {"token": (server.CONTROL / "admin-token").read_text().strip()}
        )
        self.assertEqual(code, 200)
        self.assertIn("HttpOnly", cookie)
        self.cookie = cookie.split(";")[0]

    def test_auth_origin_and_logout_revocation(self):
        self.assertEqual(self.request("/api/settings")[0], 401)
        self.assertEqual(self.request("/api/generate", {})[0], 401)
        self.assertEqual(self.request("/api/login", {"token": "wrong"})[0], 401)
        self.login()
        self.assertEqual(self.request("/api/settings")[0], 200)
        self.assertEqual(self.request("/api/logout", {}, "https://attacker.example")[0], 403)
        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/settings")[0], 401)

    def test_fresh_install_is_paused_and_empty(self):
        self.assertFalse(self.request("/api/status")[1]["schedule"]["enabled"])
        self.assertEqual(self.request("/api/editions")[1], [])

    def test_topics_preserve_legacy_archive_and_isolate_settings_and_queue(self):
        self.assertEqual(self.request("/api/topics", {"name": "Sports science"})[0], 401)
        self.login()
        legacy = server.settings()
        code, topic, _ = self.request("/api/topics", {"name": "Sports science"})
        self.assertEqual(code, 201)
        self.assertFalse(topic["enabled"])
        topic_id = topic["id"]
        query = "?topic=" + topic_id
        config = self.request("/api/settings" + query)[1]
        config.update(prompt="Follow sports science evidence.", name="Sports", enabled=True)
        self.assertEqual(self.request("/api/settings" + query, config)[0], 200)
        self.assertEqual(server.settings(), legacy)
        self.assertEqual(server.topic_catalog()[1]["name"], "Sports")
        self.assertTrue(server.topic_catalog()[1]["enabled"])
        for root, title in ((server.ROOT, "Legacy"), (server.topic_root(topic_id), "Sports")):
            with sqlite3.connect(root / "coverage.sqlite3") as db:
                db.execute(
                    "CREATE TABLE reports (id TEXT, archived_at TEXT, markdown TEXT, items_json TEXT)"
                )
                db.execute(
                    "INSERT INTO reports VALUES (?, ?, ?, '[]')",
                    (title, "2026-07-02T07:00:00Z", "# " + title),
                )
        self.assertEqual(self.request("/api/editions")[1][0]["title"], "Legacy")
        self.assertEqual(self.request("/api/editions" + query)[1][0]["title"], "Sports")
        self.assertEqual(self.request("/api/editions/2026-07-02" + query)[1]["title"], "Sports")
        server.write_json(server.CONTROL / "worker.json", {"heartbeat": time.time()})
        self.assertEqual(self.request("/api/generate" + query, {})[0], 202)
        self.assertEqual(server.read_json(server.CONTROL / "request.json", {})["topic"], topic_id)
        self.assertEqual(self.request("/api/generate", {})[0], 409)

    def test_topic_validation_and_unknown_ids(self):
        self.login()
        for name in ("", "   ", "x" * 81, [], None):
            self.assertEqual(self.request("/api/topics", {"name": name})[0], 400)
        for topic_id in ("missing", "../../journal", "%2Fetc"):
            for endpoint in ("settings", "editions", "editions/2026-07-02"):
                self.assertEqual(self.request("/api/" + endpoint + "?topic=" + topic_id)[0], 404)
            self.assertEqual(self.request("/api/generate?topic=" + topic_id, {})[0], 404)
        self.assertEqual(len(server.topic_catalog()), 1)

    def test_topic_cadences_migrate_without_changing_other_topics(self):
        server.write_json(server.CONTROL / "schedule.json", {"enabled": True, "time": "08:00"})
        self.login()
        topic = self.request("/api/topics", {"name": "Agents"})[1]
        config = self.request("/api/settings?topic=" + topic["id"])[1]
        config["schedule"] = {"enabled": True, "time": "09:30", "cadence": "weekdays", "weekday": 1}
        config["enabled"] = True
        self.assertEqual(self.request("/api/settings?topic=" + topic["id"], config)[0], 200)
        legacy = server.settings()
        self.assertEqual(
            legacy["schedule"], {"enabled": True, "time": "08:00", "cadence": "daily", "weekday": 1}
        )
        weekly = dict(
            legacy,
            prompt="Research forecast combinations.",
            lookback_days=7,
            schedule={"enabled": True, "time": "08:00", "cadence": "weekly", "weekday": 1},
        )
        self.assertEqual(self.request("/api/settings", weekly)[0], 200)
        self.assertEqual(server.settings()["schedule"], weekly["schedule"])
        self.assertEqual(server.settings(topic["id"])["schedule"], config["schedule"])
        self.assertEqual(
            server.read_json(server.CONTROL / "schedule.json", {}),
            {"enabled": True, "time": "08:00"},
        )
        public = self.request("/api/topics")[1]
        self.assertEqual(public[0]["schedule"], weekly["schedule"])
        for invalid in (
            {"cadence": "monthly"},
            {"weekday": True},
            {"weekday": 7},
            {"weekday": -1},
            {"time": None},
        ):
            bad = dict(weekly, schedule={**weekly["schedule"], **invalid})
            self.assertEqual(self.request("/api/settings", bad)[0], 400)
            self.assertEqual(server.settings()["schedule"], weekly["schedule"])

    def test_key_help_returns_command_without_exposing_key(self):
        code, help_text, _ = self.request("/api/access-key-help")
        self.assertEqual(code, 200)
        self.assertFalse(help_text["from_any_directory"])
        token = (server.CONTROL / "admin-token").read_text().strip()
        with (
            patch.object(server, "ROOT", Path("/data")),
            patch.dict(server.os.environ, {"HOSTNAME": "abcdef123456"}),
        ):
            code, help_text, _ = self.request("/api/access-key-help")
        self.assertEqual(code, 200)
        self.assertTrue(help_text["from_any_directory"])
        self.assertEqual(
            help_text["command"], "docker exec abcdef123456 cat /data/journal/admin-token"
        )
        self.assertNotIn(token, json.dumps(help_text))

    def test_untrusted_hosts_cannot_read_archive_or_login(self):
        with patch.object(server, "reports") as archive:
            for host in (
                "attacker.example",
                "localhost.attacker.example",
                "attacker.example:8097",
                "localhost@attacker.example",
                "attacker.example@localhost",
                "localhost/path",
                "localhost:invalid",
                "localhost:99999",
                "[::1",
                "",
            ):
                with self.subTest(host=host):
                    self.assertEqual(self.request("/api/editions", host=host)[0], 403)
                    self.assertEqual(self.request("/api/login", {}, host=host)[0], 403)
            archive.assert_not_called()

    def test_allowed_local_and_configured_hosts(self):
        for host in ("localhost", "LOCALHOST:8097", "127.0.0.1:8097", "[::1]:8097"):
            self.assertEqual(self.request("/api/health", host=host)[0], 200)
        self.assertEqual(self.request("/api/health", host="journal.example")[0], 403)
        with patch.object(server, "ALLOWED_HOSTS", {"journal.example"}):
            self.assertEqual(self.request("/api/health", host="journal.example:8097")[0], 200)

    def test_missing_or_duplicate_host_is_rejected(self):
        for hosts in ([], ["localhost", "attacker.example"]):
            conn = http.client.HTTPConnection("127.0.0.1", self.http.server_port)
            conn.putrequest("GET", "/api/editions", skip_host=True)
            for host in hosts:
                conn.putheader("Host", host)
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.close()

    def test_login_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.request("/api/login", {"token": "wrong"})[0], 401)
        self.assertEqual(self.request("/api/login", {"token": "wrong"})[0], 429)

    def test_settings_validation_and_queue(self):
        self.login()
        config = dict(
            prompt="Follow ensemble forecasting.",
            topics=["Forecasts"],
            sources=[],
            exclude=[],
            maximum_items=5,
            lookback_days=3,
            schedule={"enabled": False, "time": "09:15", "cadence": "daily", "weekday": 1},
        )
        self.assertEqual(self.request("/api/settings", dict(config, maximum_items=True))[0], 400)
        self.assertEqual(
            self.request(
                "/api/settings", dict(config, schedule={"enabled": True, "time": "27:00"})
            )[0],
            400,
        )
        self.assertEqual(self.request("/api/settings", config)[0], 200)
        self.assertEqual(self.request("/api/settings")[1], config)
        self.assertEqual(self.request("/api/generate", {})[0], 503)
        server.write_json(server.CONTROL / "worker.json", {"heartbeat": time.time(), "busy": False})
        self.assertEqual(self.request("/api/generate", {})[0], 202)
        self.assertEqual(self.request("/api/generate", {})[0], 409)
        self.assertTrue((server.CONTROL / "request.json").exists())

    def test_one_edition_per_london_day_latest_revision(self):
        with sqlite3.connect(server.ROOT / "coverage.sqlite3") as db:
            db.execute(
                "CREATE TABLE reports (id TEXT, archived_at TEXT, markdown TEXT, items_json TEXT)"
            )
            db.executemany(
                "INSERT INTO reports VALUES (?,?,?,?)",
                [
                    ("old", "2026-07-01T23:15:00Z", "# Old\n\nOverview.", "[]"),
                    ("new", "2026-07-02T07:00:00Z", "# New\n\nUpdated.", "[]"),
                ],
            )
        code, rows, _ = self.request("/api/editions")
        self.assertEqual(code, 200)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["date"], rows[0]["id"], rows[0]["revisions"]), ("2026-07-02", "new", 2)
        )
        self.assertNotIn("markdown", rows[0])
        self.assertEqual(
            self.request("/api/editions/2026-07-02")[1]["markdown"], "# New\n\nUpdated."
        )
        self.assertEqual(self.request("/api/editions/2026-07-03")[0], 404)
        self.assertEqual(self.request("/../server.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
