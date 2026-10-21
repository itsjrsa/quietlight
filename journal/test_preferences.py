"""Exercise terminal onboarding against the real journal API without a model."""

import contextlib
import importlib.util
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import server

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("preferences", REPO / "research/preferences.py")
preferences = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preferences)


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = patch.multiple(
            server, ROOT=self.root / "research", CONTROL=self.root / "research/journal"
        )
        self.paths.start()
        server.SESSIONS.clear()
        server.initialize()
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.template = json.loads((REPO / "research/settings.example.json").read_text())

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.paths.stop()
        self.tmp.cleanup()

    def run_command(self, *args, body=None):
        real_build = preferences.build_opener

        def local_opener(*handlers):
            opener = real_build(*handlers)
            real_open = opener.open

            def local_open(request, **kwargs):
                request.full_url = request.full_url.replace(
                    "http://journal:8097", f"http://127.0.0.1:{self.http.server_port}"
                )
                return real_open(request, **kwargs)

            opener.open = local_open
            return opener

        output = io.StringIO()
        with (
            patch.object(preferences, "build_opener", side_effect=local_opener),
            patch.dict(preferences.os.environ, {"HERMES_HOME": str(self.root)}),
            patch.object(preferences.sys, "argv", ["preferences", *args]),
            patch.object(preferences.sys, "stdin", io.StringIO(json.dumps(body))),
            contextlib.redirect_stdout(output),
        ):
            preferences.main()
        token = (server.CONTROL / "admin-token").read_text().strip()
        self.assertNotIn(token, output.getvalue())
        self.assertFalse(server.SESSIONS)
        return output.getvalue()

    def test_configure_show_schedule_and_generate(self):
        self.run_command("configure", "-", body=self.template)
        self.assertEqual(json.loads(self.run_command("show")), self.template)
        self.assertFalse((server.CONTROL / "request.json").exists())
        self.run_command("schedule", "09:30")
        self.assertEqual(
            server.settings()["schedule"],
            {"enabled": True, "time": "09:30", "cadence": "daily", "weekday": 1},
        )
        self.run_command("schedule", "off")
        self.assertFalse(server.settings()["schedule"]["enabled"])
        self.assertEqual(server.settings()["prompt"], self.template["prompt"])
        server.write_json(server.CONTROL / "worker.json", {"heartbeat": time.time()})
        self.run_command("generate")
        self.assertTrue((server.CONTROL / "request.json").exists())

    def test_invalid_input_preserves_saved_settings(self):
        self.run_command("configure", "-", body=self.template)
        before = server.settings()
        with self.assertRaises(HTTPError):
            self.run_command("configure", "-", body=dict(self.template, maximum_items=99))
        self.assertEqual(server.settings(), before)
        with self.assertRaises(ValueError):
            self.run_command("configure", "-", body={"prompt": "Incomplete settings"})
        with self.assertRaises(ValueError):
            self.run_command("schedule", "25:00")
        self.assertEqual(server.settings(), before)

    def test_first_run_templates_agree(self):
        profile = json.loads((REPO / "research/profile.example.json").read_text())
        self.assertTrue(profile["topics"])
        for setting, key in (
            ("prompt", "instructions"),
            ("sources", "preferred_sources"),
            ("topics", "topics"),
            ("exclude", "exclude"),
            ("maximum_items", "maximum_items"),
            ("lookback_days", "lookback_days"),
        ):
            self.assertEqual(self.template[setting], profile[key])
        self.assertFalse(self.template["schedule"]["enabled"])
