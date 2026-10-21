"""Ephemeral browser-test server (not a unittest module); synthetic content only."""

import json
import sys
import tempfile
from pathlib import Path

import server

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
from ledger import archive  # noqa: E402

with tempfile.TemporaryDirectory(prefix="quietlight-ui-") as temporary:
    server.ROOT = Path(temporary)
    server.CONTROL = server.ROOT / "journal"
    server.initialize()
    server.write_json(
        server.ROOT / "profile.json",
        {
            "instructions": "Follow original research and explain its practical significance.",
            "topics": ["Research methods"],
        },
    )
    archive(
        server.ROOT,
        "# A clearer view of research\n\nIllustrative test content, not a real finding.\n\n## One useful idea\n\nRead the [example source](https://example.org/research).",
        [
            {"title": "A clearer view of research", "url": "https://example.org/research"},
        ],
    )
    server.write_json(
        server.CONTROL / "topics.json",
        [
            {"id": "default", "name": "Your journal", "enabled": True},
            {
                "id": "space",
                "name": "Space science",
                "enabled": True,
                "schedule": {"enabled": True, "time": "08:00", "cadence": "weekly", "weekday": 1},
            },
        ],
    )
    space = server.topic_root("space")
    space.mkdir(parents=True)
    server.write_json(
        space / "profile.json",
        {
            "instructions": "Follow original research about space exploration.",
            "topics": ["Space science"],
        },
    )
    archive(
        space,
        "# A view beyond Earth\n\nIllustrative space research fixture.\n\n## A different perspective\n\nRead the [example source](https://example.org/space).",
        [
            {"title": "A view beyond Earth", "url": "https://example.org/space"},
        ],
    )
    http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    # A short-lived test key over a private pipe, never written to screenshots or logs.
    print(
        json.dumps(
            {
                "port": http.server_port,
                "token": (server.CONTROL / "admin-token").read_text().strip(),
            }
        ),
        flush=True,
    )
    http.serve_forever()
