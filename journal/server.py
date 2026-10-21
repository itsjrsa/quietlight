"""Private-network research journal. No model credentials or Docker access."""

import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("RESEARCH_ROOT", "/data"))
STATIC = Path(__file__).parent / "static"
CONTROL = ROOT / "journal"
LOCK = threading.Lock()
SESSIONS = {}
ATTEMPTS = {}
AUTH_LOCK = threading.Lock()
DEFAULT_SCHEDULE = {"enabled": False, "time": "08:00"}
ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.environ.get("JOURNAL_ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",")
    if host.strip()
}


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write_json(path, data):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def initialize():
    os.umask(0o077)
    CONTROL.mkdir(parents=True, exist_ok=True)
    token = CONTROL / "admin-token"
    if not token.exists():
        with token.open("x") as handle:
            handle.write(secrets.token_urlsafe(24) + "\n")


def plain(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*_`#]", "", text).strip()


def topic_catalog():
    return read_json(
        CONTROL / "topics.json", [{"id": "default", "name": "Your journal", "enabled": True}]
    )


def topic_root(topic_id):
    if not any(t["id"] == topic_id for t in topic_catalog()):
        raise ValueError("Unknown topic")
    return ROOT if topic_id == "default" else ROOT / "topics" / topic_id


def topic_schedule(topic):
    # The old shared file is a frozen fallback for topics not yet edited.
    return {
        "cadence": "daily",
        "weekday": 1,
        **topic.get("schedule", read_json(CONTROL / "schedule.json", DEFAULT_SCHEDULE)),
    }


def reports(topic_id="default"):
    path = topic_root(topic_id) / "coverage.sqlite3"
    if not path.exists():
        return []
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT id,archived_at,markdown,items_json FROM reports ORDER BY archived_at DESC, rowid DESC"
        ).fetchall()
    finally:
        db.close()
    result = []
    for row in rows:
        date = (
            datetime.fromisoformat(row["archived_at"].replace("Z", "+00:00"))
            .astimezone(ZoneInfo("Europe/London"))
            .date()
            .isoformat()
        )
        md = row["markdown"]
        items = json.loads(row["items_json"])
        paragraphs = [p.strip() for p in md.split("\n\n") if p.strip() and not p.startswith("#")]
        summary = plain(paragraphs[0] if paragraphs else "A new edition of your research briefing.")
        summary = re.sub(r"^Overview\.?\s*", "", summary)
        heading = next((line[2:].strip() for line in md.splitlines() if line.startswith("# ")), "")
        generic = not heading or bool(
            re.search(r"morning research|daily.*brief|\d{4}", heading, re.I)
        )
        title = (
            plain(items[0]["title"])
            if generic and items
            else plain(heading) or "Your research briefing"
        )
        result.append(
            dict(
                id=row["id"],
                date=date,
                archived_at=row["archived_at"],
                title=title,
                summary=summary,
                minutes=max(1, round(len(md.split()) / 210)),
                items=items,
                markdown=md,
            )
        )
    return result


def settings(topic_id="default"):
    profile = read_json(topic_root(topic_id) / "profile.json", {})
    schedule = topic_schedule(next(t for t in topic_catalog() if t["id"] == topic_id))
    return dict(
        prompt=profile.get("instructions", ""),
        topics=profile.get("topics", []),
        sources=profile.get("preferred_sources", []),
        exclude=profile.get("exclude", []),
        maximum_items=profile.get("maximum_items", 8),
        lookback_days=profile.get("lookback_days", 3),
        schedule=schedule,
    )


def status(topic_id="default"):
    state = read_json(CONTROL / "worker.json", {})
    fresh = time.time() - state.get("heartbeat", 0) < 90
    pending = (CONTROL / "request.json").exists()
    queued = read_json(CONTROL / "request.json", {}).get("topic") == topic_id
    inflight = read_json(CONTROL / "inflight.json", {}).get("topic") == topic_id
    started = state.get("active_topics", {}).get(topic_id)
    events = read_json(topic_root(topic_id) / "progress.json", [])
    events = (
        [
            e
            for e in events
            if isinstance(e, dict)
            and isinstance(e.get("at"), (int, float))
            and started is not None
            and e["at"] >= started
        ][-60:]
        if isinstance(events, list)
        else []
    )
    return dict(
        online=fresh,
        busy=(state.get("busy", False) and fresh) or pending,
        pending=pending,
        research=dict(
            active=bool((started is not None or inflight) and fresh),
            queued=queued,
            started_at=started,
            events=events,
        ),
        last_error=state.get("last_error"),
        last_completed=state.get("last_completed"),
        stage=state.get("stage", "offline"),
        schedule=topic_schedule(next(t for t in topic_catalog() if t["id"] == "default")),
    )


class Handler(BaseHTTPRequestHandler):
    def parse_request(self):
        if not super().parse_request():
            return False
        # Check every route before reading private state, including unauthenticated GETs.
        hosts = self.headers.get_all("Host", [])
        valid = False
        if len(hosts) == 1:
            host = hosts[0]
            try:
                authority = urlsplit("//" + host)
                valid = (
                    bool(host)
                    and not re.search(r"[\s\\]", host)
                    and authority.netloc == host
                    and authority.username is None
                    and authority.password is None
                    and authority.hostname in ALLOWED_HOSTS
                    and (authority.port is None or 1 <= authority.port <= 65535)
                )
            except ValueError:
                pass
        if not valid:
            self.close_connection = True
            self.send(403, {"error": "Host not allowed. Check JOURNAL_ALLOWED_HOSTS."})
            return False
        return True

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt, *args):
        pass  # Request bodies, access keys, and cookies never enter logs.

    def send(self, code, body, content_type="application/json", headers=None):
        data = json.dumps(body).encode() if content_type == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Cache-Control", "no-store" if content_type == "application/json" else "no-cache"
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'",
        )
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        cookies = dict(
            part.strip().split("=", 1)
            for part in self.headers.get("Cookie", "").split(";")
            if "=" in part
        )
        key = cookies.get("journal_session", "")
        with AUTH_LOCK:
            return SESSIONS.get(key, 0) > time.time()

    def login(self, supplied):
        """Bound authentication state and serialize rate-limit/session updates."""
        now = time.time()
        ip = self.client_address[0]
        with AUTH_LOCK:
            for key, expiry in list(SESSIONS.items()):
                if expiry <= now:
                    del SESSIONS[key]
            for address, failures in list(ATTEMPTS.items()):
                recent = [stamp for stamp in failures if stamp > now - 300]
                if recent:
                    ATTEMPTS[address] = recent
                else:
                    del ATTEMPTS[address]
            if ip not in ATTEMPTS and len(ATTEMPTS) >= 4096:
                return self.send(429, {"error": "Try again in five minutes."})
            attempts = ATTEMPTS.setdefault(ip, [])
            if len(attempts) >= 10:
                return self.send(429, {"error": "Too many attempts. Try again in five minutes."})
            expected = (CONTROL / "admin-token").read_text().strip()
            if not hmac.compare_digest(str(supplied).encode(), expected.encode()):
                attempts.append(now)
                return self.send(401, {"error": "That access key did not match."})
            if len(SESSIONS) >= 128:
                del SESSIONS[next(iter(SESSIONS))]
            session = secrets.token_urlsafe(32)
            SESSIONS[session] = now + 86400
            ATTEMPTS.pop(ip, None)
        return self.send(
            200,
            {"ok": True},
            headers={
                "Set-Cookie": f"journal_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400"
            },
        )

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            topic_id = parse_qs(urlsplit(self.path).query).get("topic", ["default"])[0]
            if path in ("/api/settings", "/api/editions", "/api/status") or path.startswith(
                "/api/editions/"
            ):
                if not any(t["id"] == topic_id for t in topic_catalog()):
                    return self.send(404, {"error": "Topic not found"})
            if path == "/api/topics":
                return self.send(
                    200, [dict(t, schedule=topic_schedule(t)) for t in topic_catalog()]
                )
            if path == "/api/health":
                return self.send(200, {"ok": True})
            if path == "/api/access-key-help":
                container = os.environ.get("HOSTNAME", "")
                direct = ROOT == Path("/data") and bool(re.fullmatch(r"[a-f0-9]{12,64}", container))
                return self.send(
                    200,
                    {
                        "command": f"docker exec {container} cat /data/journal/admin-token"
                        if direct
                        else "docker compose exec journal cat /data/journal/admin-token",
                        "from_any_directory": direct,
                    },
                )
            if path == "/api/session":
                return self.send(200, {"authenticated": self.authorized()})
            if path == "/api/status":
                return self.send(200, status(topic_id))
            if path == "/api/editions":
                by_day = {}
                for report in reports(topic_id):
                    if report["date"] not in by_day:
                        by_day[report["date"]] = {
                            k: v for k, v in report.items() if k != "markdown"
                        }
                        by_day[report["date"]]["revisions"] = 0
                    by_day[report["date"]]["revisions"] += 1
                return self.send(200, list(by_day.values()))
            if re.fullmatch(r"/api/editions/\d{4}-\d{2}-\d{2}", path):
                day = path.rsplit("/", 1)[1]
                report = next((r for r in reports(topic_id) if r["date"] == day), None)
                return self.send(200 if report else 404, report or {"error": "Edition not found"})
            if path == "/api/settings":
                if not self.authorized():
                    return self.send(401, {"error": "Unlock settings first"})
                return self.send(200, settings(topic_id))
            if (
                path == "/"
                or path == "/settings"
                or re.fullmatch(r"/topics/[a-z0-9-]+(?:/edition/\d{4}-\d{2}-\d{2})?", path)
                or re.fullmatch(r"/edition/\d{4}-\d{2}-\d{2}", path)
            ):
                return self.send(
                    200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8"
                )
            file = (STATIC / path.lstrip("/")).resolve()
            if not file.is_relative_to(STATIC.resolve()) or not file.is_file():
                return self.send(404, {"error": "Not found"})
            content_type = {
                ".js": "text/javascript",
                ".css": "text/css",
                ".svg": "image/svg+xml",
            }.get(file.suffix, "application/octet-stream")
            return self.send(200, file.read_bytes(), content_type)
        except (OSError, ValueError, sqlite3.Error):
            return self.send(
                503, {"error": "The archive is temporarily unavailable. Please retry."}
            )

    def do_POST(self):
        try:
            origin = self.headers.get("Origin", "")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.send(403, {"error": "Cross-origin request refused"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "JSON required"})
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 50000:
                return self.send(413, {"error": "Invalid request size"})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Expected an object")
            path = urlsplit(self.path).path
            if path == "/api/login":
                return self.login(body.get("token", ""))
            if not self.authorized():
                return self.send(401, {"error": "Unlock settings first"})
            topic_id = parse_qs(urlsplit(self.path).query).get("topic", ["default"])[0]
            if path in ("/api/settings", "/api/generate"):
                if not any(t["id"] == topic_id for t in topic_catalog()):
                    return self.send(404, {"error": "Topic not found"})
            if path == "/api/topics":
                name = body.get("name", "")
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                    raise ValueError("Choose a topic name")
                with LOCK:
                    catalog = topic_catalog()
                    if len(catalog) >= 20:
                        return self.send(400, {"error": "You can follow up to 20 topics."})
                    entry = {"id": secrets.token_hex(6), "name": name.strip(), "enabled": False}
                    root = ROOT / "topics" / entry["id"]
                    root.mkdir(parents=True, exist_ok=True)
                    write_json(
                        root / "profile.json",
                        {
                            "instructions": "Research significant developments in "
                            + name.strip()
                            + ".",
                            "topics": [name.strip()],
                            "preferred_sources": [],
                            "exclude": [],
                            "maximum_items": 5,
                            "lookback_days": 3,
                        },
                    )
                    write_json(CONTROL / "topics.json", [*catalog, entry])
                return self.send(201, entry)
            if path == "/api/logout":
                cookies = dict(
                    part.strip().split("=", 1)
                    for part in self.headers.get("Cookie", "").split(";")
                    if "=" in part
                )
                with AUTH_LOCK:
                    SESSIONS.pop(cookies.get("journal_session", ""), None)
                return self.send(
                    200,
                    {"ok": True},
                    headers={
                        "Set-Cookie": "journal_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                    },
                )
            if path == "/api/generate":
                with LOCK:
                    current = status()
                    if not current["online"]:
                        return self.send(503, {"error": "The research service is offline."})
                    if current["busy"]:
                        return self.send(409, {"error": "A briefing is already in progress."})
                    write_json(
                        CONTROL / "request.json",
                        {"id": secrets.token_hex(12), "created": time.time(), "topic": topic_id},
                    )
                return self.send(202, {"ok": True})
            if path == "/api/settings":
                if "name" in body and (
                    not isinstance(body["name"], str) or not 1 <= len(body["name"].strip()) <= 80
                ):
                    raise ValueError("Invalid topic name")
                if "enabled" in body and type(body["enabled"]) is not bool:
                    raise ValueError("Invalid topic pause setting")
                prompt = body.get("prompt", "")
                if not isinstance(prompt, str) or not 10 <= len(prompt.strip()) <= 12000:
                    raise ValueError("Describe your research interests in 10–12,000 characters.")
                for key in ("topics", "sources", "exclude"):
                    values = body.get(key, [])
                    if (
                        not isinstance(values, list)
                        or len(values) > 40
                        or any(not isinstance(v, str) or len(v) > 2000 for v in values)
                    ):
                        raise ValueError(f"Invalid {key}")
                maximum, lookback = body.get("maximum_items"), body.get("lookback_days")
                if (
                    type(maximum) is not int
                    or not 1 <= maximum <= 12
                    or type(lookback) is not int
                    or not 1 <= lookback <= 30
                ):
                    raise ValueError("Choose 1–12 stories and a 1–30 day lookback.")
                schedule = body.get("schedule", {})
                if (
                    not isinstance(schedule, dict)
                    or type(schedule.get("enabled")) is not bool
                    or not isinstance(schedule.get("time"), str)
                    or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule.get("time", ""))
                    or schedule.get("cadence", "daily") not in ("daily", "weekdays", "weekly")
                    or type(schedule.get("weekday", 1)) is not int
                    or not 0 <= schedule.get("weekday", 1) <= 6
                ):
                    raise ValueError("Choose a valid research schedule.")
                with LOCK:
                    root = topic_root(topic_id)
                    profile = read_json(root / "profile.json", {})
                    profile.update(
                        instructions=prompt.strip(),
                        topics=body.get("topics") or [prompt.strip()],
                        preferred_sources=body.get("sources", []),
                        exclude=body.get("exclude", []),
                        maximum_items=maximum,
                        lookback_days=lookback,
                    )
                    write_json(root / "profile.json", profile)
                    catalog = topic_catalog()
                    for topic in catalog:
                        if topic["id"] == topic_id:
                            topic["name"] = body.get("name", topic["name"]).strip()
                            topic["enabled"] = body.get("enabled", topic["enabled"])
                            topic["schedule"] = {
                                "enabled": schedule["enabled"],
                                "time": schedule["time"],
                                "cadence": schedule.get("cadence", "daily"),
                                "weekday": schedule.get("weekday", 1),
                            }
                    write_json(CONTROL / "topics.json", catalog)
                return self.send(200, {"ok": True})
            self.send(404, {"error": "Not found"})
        except (ValueError, TypeError):
            self.send(
                400,
                {
                    "error": "Check your settings: use a research prompt, valid lists, a time, and numbers within the shown limits."
                },
            )
        except OSError:
            self.send(503, {"error": "Settings could not be saved. Please retry."})


if __name__ == "__main__":
    initialize()
    print("Journal listening on port " + os.environ.get("PORT", "8097"), flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8097"))), Handler).serve_forever()
