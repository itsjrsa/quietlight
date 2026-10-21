#!/usr/bin/env python3
"""Prove the real scanner rejects a synthetic token and never prints its value."""

import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="quietlight-scanner-") as temporary:
    root = Path(temporary)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    shutil.copyfile(source / ".gitleaks.toml", root / ".gitleaks.toml")
    note = root / "notes.txt"
    note.write_text("Ordinary test content")
    subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
    command = ["bash", str(source / "scripts/check-secrets.sh"), "staged"]
    clean = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if clean.returncode:
        raise SystemExit("Scanner could not pass the clean fixture; inspect Docker availability.")
    fake = "ghp_" + secrets.token_hex(20)
    note.write_text(fake)
    subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
    unsafe = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if unsafe.returncode != 1 or "leaks found" not in unsafe.stdout:
        raise SystemExit("Scanner did not reject the synthetic credential as expected.")
    if fake in unsafe.stdout + unsafe.stderr:
        raise SystemExit("Scanner output was not redacted.")
    print("PASS: clean snapshot accepted; synthetic credential blocked; output redacted.")
