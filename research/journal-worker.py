#!/usr/bin/env python3
"""Run the Hermes gateway and bridge the journal's narrow request queue to cron."""

import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

HOME_DIR = Path(os.environ.get("HERMES_HOME", "/opt/data"))
CONTROL = HOME_DIR / "research" / "journal"
JOB = "morning-research"
STATE = {"busy": False, "stage": "starting", "last_error": None}
STOP = threading.Event()


def read(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def write(path, value):
    temp = path.with_name(path.name + ".worker-tmp")
    temp.write_text(json.dumps(value))
    os.replace(temp, path)


def topics():
    return read(
        HOME_DIR / "research" / "journal" / "topics.json",
        [{"id": "default", "name": "Your journal", "enabled": True}],
    )


def topic_root(topic_id):
    if not re.fullmatch(r"[a-z0-9-]+", topic_id):
        raise ValueError("Invalid topic identifier")
    root = HOME_DIR / "research"
    return root if topic_id == "default" else root / "topics" / topic_id


def job_name(topic_id):
    return JOB if topic_id == "default" else JOB + "-" + topic_id


def job(name=JOB):
    return next(
        (
            j
            for j in read(HOME_DIR / "cron" / "jobs.json", {}).get("jobs", [])
            if j.get("name") == name
        ),
        {},
    )


def active_topics():
    path = HOME_DIR / "cron" / "executions.db"
    if not path.exists():
        return []
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as db:
            return [
                topic["id"]
                for topic in topics()
                if db.execute(
                    "SELECT 1 FROM executions WHERE job_id=? AND status IN ('claimed','running') LIMIT 1",
                    (job(job_name(topic["id"])).get("id"),),
                ).fetchone()
            ]
    except sqlite3.Error:
        # An unreadable execution ledger is not evidence that it is idle.
        return None


def active():
    running = active_topics()
    return running is None or bool(running)


def heartbeat():
    started = {}
    while not STOP.is_set():
        now = time.time()
        running = active_topics()
        ids = set(running or [])
        if STATE.get("topic") and STATE["busy"]:
            ids.add(STATE["topic"])
        started = {topic: started.get(topic, now - 5) for topic in ids}
        value = dict(
            STATE,
            heartbeat=now,
            busy=STATE["busy"] or running is None or bool(ids),
            active_topics=started,
        )
        failed = [
            t["name"]
            for t in topics()
            if job(job_name(t["id"])).get("last_status") in ("failed", "error", "blocked_config")
        ]
        if failed:
            value["last_error"] = (
                "Scheduled research failed for "
                + ", ".join(failed)
                + ". Check Hermes cron history."
            )
        write(CONTROL / "worker.json", value)
        STOP.wait(5)


def cli(*args):
    # Existing CLI does all job validation, locking, and provider work.
    result = subprocess.run(["hermes", "cron", *args], capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise RuntimeError("Hermes command failed; inspect cron history for details.")
    if args[0] == "run" and "succeeded" not in result.stdout:
        raise RuntimeError("Hermes did not confirm a completed briefing. Inspect cron history.")
    return result


def stop(*_):
    STOP.set()


def archive_count(topic_id="default"):
    """Only a newly persisted edition counts as a successful publication."""
    path = topic_root(topic_id) / "coverage.sqlite3"
    if not path.exists():
        return 0
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as db:
        return db.execute("SELECT count(*) FROM reports").fetchone()[0]


def run_briefing(topic_id="default"):
    before = archive_count(topic_id)
    cli("run", job_name(topic_id))
    if archive_count(topic_id) <= before:
        raise RuntimeError(
            "Research finished without a new archived edition. Inspect cron history."
        )
    STATE["last_completed"] = time.time()


def cron_expression(schedule):
    hour, minute = map(int, schedule["time"].split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Invalid publishing time")
    cadence = schedule.get("cadence", "daily")
    weekday = schedule.get("weekday", 1)
    if (
        cadence not in ("daily", "weekdays", "weekly")
        or type(weekday) is not int
        or not 0 <= weekday <= 6
    ):
        raise ValueError("Invalid research cadence")
    days = str(weekday) if cadence == "weekly" else "1-5" if cadence == "weekdays" else "*"
    return f"{minute} {hour} * * {days}"


def configure_jobs(fallback_schedule, catalog):
    template = Path(__file__).with_name("briefing.txt").read_text()
    for topic in catalog:
        schedule = topic.get("schedule", fallback_schedule)
        expression = cron_expression(schedule)
        root = topic_root(topic["id"])
        root.mkdir(parents=True, exist_ok=True)
        # Each prompt pins all profile, draft, and ledger paths to this topic.
        prompt = template.replace("/opt/data/research", str(root)).replace(
            "ledger.py ", f"ledger.py --root {root} "
        )
        name = job_name(topic["id"])
        if not job(name):
            cli(
                "create",
                expression,
                prompt,
                "--name",
                name,
                "--deliver",
                "local",
                "--workdir",
                str(root),
                "--paused",
            )
        cli(
            "edit",
            name,
            "--schedule",
            expression,
            "--deliver",
            "local",
            "--prompt",
            prompt,
        )
        cli("resume" if schedule["enabled"] and topic["enabled"] else "pause", name)


def main():
    os.umask(0o077)
    CONTROL.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if (CONTROL / "inflight.json").exists():
        STATE["last_error"] = (
            "A generation was interrupted by a restart. Check the archive before retrying."
        )
        (CONTROL / "inflight.json").unlink()
    gateway = subprocess.Popen(["hermes", "gateway", "run"])
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    applied = None
    STOP.wait(15)
    try:
        while not STOP.is_set():
            if gateway.poll() is not None:
                raise RuntimeError("Gateway exited. The container will restart.")
            schedule = read(CONTROL / "schedule.json", {"enabled": False, "time": "08:00"})
            catalog = topics()
            try:
                if not active() and (schedule, catalog) != applied:
                    configure_jobs(schedule, catalog)
                    applied = (dict(schedule), catalog)
                    STATE["stage"] = "ready"
                request = CONTROL / "request.json"
                if request.exists() and not active():
                    topic_id = read(request, {}).get("topic", "default")
                    topic = next((t for t in catalog if t["id"] == topic_id), None)
                    if topic is None:
                        raise ValueError("Requested topic no longer exists")
                    paused = not (topic.get("schedule", schedule)["enabled"] and topic["enabled"])
                    name = job_name(topic_id)
                    os.replace(request, CONTROL / "inflight.json")
                    STATE.update(busy=True, stage="researching", last_error=None, topic=topic_id)
                    try:
                        if paused:
                            cli("resume", name)
                        run_briefing(topic_id)
                    finally:
                        try:
                            if paused:
                                cli("pause", name)
                        finally:
                            # Re-apply the intended schedule after any failure.
                            applied = None
                            (CONTROL / "inflight.json").unlink(missing_ok=True)
                            STATE.update(busy=False, stage="ready")
            except (
                RuntimeError,
                ValueError,
                OSError,
                sqlite3.Error,
                subprocess.TimeoutExpired,
            ) as exc:
                STATE.update(last_error=str(exc), busy=False, stage="error")
            STOP.wait(5)
    finally:
        STOP.set()
        gateway.terminate()
        try:
            gateway.wait(timeout=15)
        except subprocess.TimeoutExpired:
            gateway.kill()
        thread.join(timeout=6)
        write(CONTROL / "worker.json", dict(STATE, heartbeat=0, busy=False, stage="offline"))


if __name__ == "__main__":
    main()
