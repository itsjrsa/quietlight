#!/usr/bin/env python3
"""Reject private material without printing its contents. Default: exact Git index."""

import argparse
import hashlib
import ipaddress
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

LOCAL_ADDRESSES = {"127.0.0.1", "0.0.0.0", "::1", "::"}
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6 = re.compile(r"(?<![\w:])(?:[a-fA-F0-9]{0,4}:){2,}[a-fA-F0-9:.]{0,45}(?![\w:])")
PRIVATE_PATH = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/")
CREDENTIAL = re.compile(
    r"""(?i)["']?(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)["']?\s*[:=]\s*["']([^"'\n]+)["']"""
)
URL_AUTH = re.compile(r"https?://[^\s/@:]+:[^\s/@]+@", re.I)
BARE_CREDENTIAL = re.compile(
    r"(?i)^\s*(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\s*[:=]\s*([^\s\"'${<#][^\s#]*)\s*(?:#.*)?$"
)
SAFE_VALUES = {"", "example", "placeholder", "changeme", "your_key_here", "redacted"}
PRIVATE_NAMES = {
    "auth.json",
    "credentials.json",
    "admin-token",
    "id_rsa",
    "id_ed25519",
    ".npmrc",
    ".netrc",
}
PRIVATE_DIRS = {"data", "backups", "logs", "test-results", "node_modules", ".venv", ".vupai"}
PRIVATE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".log", ".zip", ".gz", ".tar"}

# Visually reviewed screenshots of synthetic ui_fixture.py content only.
# Pin both path and bytes: replacements require a fresh privacy review.
REVIEWED_IMAGES = {
    "docs/images/quietlight-light.png": "09f6d05463a8962397b291926fe352888eb7810afdb27893806710285be02e2d",
    "docs/images/quietlight-dark.png": "a9538f6607d46f36c7f39bb362b0b57a937e4d47a438d0f6a5bcc1837f52eb62",
}


def findings(name, content, mode="100644"):
    """Return line/reason pairs, never the matching value."""
    path = PurePosixPath(name)
    problems = []
    if (
        any(part in PRIVATE_DIRS for part in path.parts)
        or path.name in PRIVATE_NAMES
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.suffix in PRIVATE_SUFFIXES
        or "static/assets" in str(path)
    ):
        problems.append((1, "private or generated file must not be committed"))
    if mode not in {"100644", "100755"}:
        problems.append((1, "symlinks and submodules require a separate review"))
    if name in REVIEWED_IMAGES and hashlib.sha256(content).hexdigest() == REVIEWED_IMAGES[name]:
        return problems
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return problems + [(1, "binary file requires a separate privacy review")]
    if "\0" in text:
        problems.append((1, "binary file requires a separate privacy review"))
    for number, line in enumerate(text.splitlines(), 1):
        for candidate in IPV4.findall(line) + IPV6.findall(line):
            try:
                address = str(ipaddress.ip_address(candidate))
            except ValueError:
                continue
            if address not in LOCAL_ADDRESSES:
                problems.append((number, "non-local IP address"))
        if PRIVATE_PATH.search(line):
            problems.append((number, "personal machine path"))
        if URL_AUTH.search(line):
            problems.append((number, "credentials embedded in URL"))
        for match in CREDENTIAL.finditer(line):
            value = match.group(1)
            if value.lower() not in SAFE_VALUES and not value.startswith(("${", "<")):
                problems.append((number, "literal credential value"))
        bare = BARE_CREDENTIAL.fullmatch(line)
        if bare and bare.group(1).lower() not in SAFE_VALUES:
            problems.append((number, "unquoted credential value"))
        if re.search(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----", line):
            problems.append((number, "private key material"))
    return sorted(set(problems))


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd)


def scan(root, worktree=False):
    """Scan all files in the index, including unchanged files; never a mixed diff."""
    entries = {}
    for record in git("ls-files", "--stage", "-z", cwd=root).split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, blob, stage = metadata.decode().split()
        if stage != "0":
            raise ValueError("Resolve merge conflicts before scanning")
        entries[name.decode()] = (mode, blob)
    if worktree:
        for name in git("ls-files", "--others", "--exclude-standard", "-z", cwd=root).split(b"\0"):
            if name:
                entries[name.decode()] = ("100644", None)
    problems = []
    for name, (mode, blob) in sorted(entries.items()):
        if worktree:
            path = root / name
            if path.is_symlink():
                problems.append((name, 1, "symlink cannot be scanned safely"))
                continue
            if not path.exists():
                continue
            content = path.read_bytes()
        else:
            content = git("cat-file", "blob", blob, cwd=root) if mode != "160000" else b""
        problems.extend((name, line, reason) for line, reason in findings(name, content, mode))
    return entries, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--worktree",
        action="store_true",
        help="include untracked, nonignored source before staging",
    )
    scope.add_argument(
        "--history", action="store_true", help="check all reachable historical blobs"
    )
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    try:
        entries, problems = scan_history(root) if args.history else scan(root, args.worktree)
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("Privacy scan could not complete; refusing to pass.", file=sys.stderr)
        return 1
    for name, line, reason in problems:
        print(f"{name}:{line}: {reason}", file=sys.stderr)
    if not entries:
        print("No source files to check; refusing an empty scan.", file=sys.stderr)
        return 1
    if problems:
        print("Remove private data. Do not bypass the hook to publish it.", file=sys.stderr)
        return 1
    print(f"Privacy check passed: {len(entries)} source files; matched values never logged.")
    return 0


def scan_history(root):
    """Catch private data removed in later commits, not only today's tree."""
    seen = set()
    problems = []
    for commit in git("rev-list", "--all", cwd=root).decode().splitlines():
        for record in git("ls-tree", "-r", "-z", commit, cwd=root).split(b"\0"):
            if not record:
                continue
            metadata, name = record.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            name = name.decode()
            key = (name, mode, blob)
            if key in seen:
                continue
            seen.add(key)
            content = git("cat-file", "blob", blob, cwd=root) if kind == "blob" else b""
            problems.extend(
                (f"{commit[:12]}:{name}", line, reason)
                for line, reason in findings(name, content, mode)
            )
    return seen, problems


if __name__ == "__main__":
    sys.exit(main())
