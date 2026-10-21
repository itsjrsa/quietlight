#!/usr/bin/env python3
"""Local research archive and coverage history; never asserts remote delivery."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def identity(item):
    if (
        not isinstance(item, dict)
        or not isinstance(item.get("title"), str)
        or not item["title"].strip()
    ):
        raise ValueError("Each item needs a nonempty title")
    url = urlsplit(item.get("url", ""))
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise ValueError("Each item needs an HTTP(S) source URL without credentials")
    doi = item.get("doi", "").strip()
    if doi:
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi, flags=re.I)
        if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
            raise ValueError("Invalid DOI")
        return "doi:" + doi.lower()
    arxiv = item.get("arxiv_id", "").strip()
    if arxiv:
        if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(?:v\d+)?", arxiv, re.I):
            raise ValueError("Invalid arXiv identifier")
        return "arxiv:" + re.sub(r"v\d+$", "", arxiv).lower()
    query = [
        (k, v)
        for k, v in parse_qsl(url.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (url.scheme.lower(), url.netloc.lower(), url.path or "/", urlencode(sorted(query)), "")
    )


def connect(root):
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "coverage.sqlite3", timeout=30)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, archived_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            markdown TEXT NOT NULL, items_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coverage (
            report_id TEXT NOT NULL REFERENCES reports(id), identity TEXT NOT NULL,
            title TEXT NOT NULL, url TEXT NOT NULL, PRIMARY KEY(report_id, identity)
        );
    """)
    return db


def archive(root, markdown, items):
    if not markdown.strip() or not isinstance(items, list):
        raise ValueError("A nonempty Markdown report and JSON array are required")
    validated = [(identity(item), item["title"], item["url"]) for item in items]
    payload = json.dumps(items, sort_keys=True, ensure_ascii=False)
    report_id = hashlib.sha256((markdown + "\0" + payload).encode()).hexdigest()
    db = connect(root)
    try:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO reports(id,markdown,items_json) VALUES(?,?,?)",
                (report_id, markdown, payload),
            )
            db.executemany(
                "INSERT OR IGNORE INTO coverage VALUES(?,?,?,?)",
                [(report_id, *entry) for entry in validated],
            )
    finally:
        db.close()
    # SQLite is authoritative. A retry regenerates the file if export was interrupted.
    output = root / "reports" / (report_id + ".md")
    output.parent.mkdir(exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return {
        "status": "archived_locally",
        "report_id": report_id,
        "path": str(output),
        "delivery": "not tracked here; inspect Hermes cron history",
    }


def recent(root, days):
    db = connect(root)
    db.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in db.execute(
                """
            SELECT r.archived_at, c.identity, c.title, c.url, r.id AS report_id
            FROM coverage c JOIN reports r ON r.id=c.report_id
            WHERE r.archived_at >= strftime('%Y-%m-%dT%H:%M:%SZ','now', ?)
            ORDER BY r.archived_at DESC LIMIT 300
        """,
                (f"-{days} days",),
            )
        ]
    finally:
        db.close()


def progress(root, stage, message, url=None):
    if not message.strip() or len(message) > 400:
        raise ValueError("Progress needs a message of 1–400 characters")
    if url:
        identity({"title": message, "url": url})
        if len(url) > 2048:
            raise ValueError("Source URL is too long")
    root.mkdir(parents=True, exist_ok=True)
    path = root / "progress.json"
    try:
        events = json.loads(path.read_text())
    except (OSError, ValueError):
        events = []
    if stage == "starting" or not isinstance(events, list):
        events = []
    event = dict(stage=stage, message=message.strip(), url=url, at=time.time())
    events = (events + [event])[-60:]
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(events))
    os.replace(temp, path)
    return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/opt/data/research"))
    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("recent")
    read.add_argument("--days", type=int, default=30)
    write = sub.add_parser("archive")
    write.add_argument("--report", type=Path, required=True)
    write.add_argument("--items", type=Path, required=True)
    update = sub.add_parser("progress")
    update.add_argument(
        "stage", choices=["starting", "searching", "reading", "reviewed", "unavailable", "writing"]
    )
    update.add_argument("message")
    update.add_argument("--url")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "recent":
            if not 1 <= args.days <= 3650:
                raise ValueError("days must be between 1 and 3650")
            result = recent(args.root, args.days)
        elif args.command == "progress":
            result = progress(args.root, args.stage, args.message, args.url)
        else:
            result = archive(
                args.root,
                args.report.read_text(encoding="utf-8"),
                json.loads(args.items.read_text(encoding="utf-8")),
            )
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Archive error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
