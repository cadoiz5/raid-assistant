#!/usr/bin/env python3
"""
updater.py - dead-simple self-update for a git checkout of raid-assistant.

If the app is running from a `git clone`, it can notice when `origin/main`
has new commits and fast-forward onto them. Anything else - a zip download,
git not installed, no network - just makes the feature quietly unavailable.

No GitHub API, no tokens: it shells out to `git`.
"""

import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BRANCH = "main"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # keep console from flashing on Windows


def _git(*args, timeout=15):
    try:
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True,
                              text=True, timeout=timeout, creationflags=_NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError):
        return None


def available():
    """True when a self-update can even be attempted: git on PATH and HERE is
    inside a work tree."""
    if not shutil.which("git"):
        return False
    r = _git("rev-parse", "--is-inside-work-tree")
    return bool(r) and r.returncode == 0 and r.stdout.strip() == "true"


def check():
    """Fetch and compare against origin/BRANCH.

    -> {'behind': int, 'ahead': int, 'subjects': [str], 'dirty': bool}
       or None if the check couldn't run (offline, not a checkout, ...).
    """
    if not available():
        return None
    fetch = _git("fetch", "--quiet", "origin", BRANCH)
    if not fetch or fetch.returncode != 0:
        return None
    rev = _git("rev-list", "--left-right", "--count", f"HEAD...origin/{BRANCH}")
    if not rev or rev.returncode != 0:
        return None
    try:
        ahead, behind = (int(x) for x in rev.stdout.split())
    except ValueError:
        return None
    subjects = []
    if behind:
        log = _git("log", "--format=%s", f"HEAD..origin/{BRANCH}")
        if log and log.returncode == 0:
            subjects = [s for s in log.stdout.splitlines() if s][:20]
    status = _git("status", "--porcelain")
    dirty = bool(status and status.stdout.strip())
    return {"behind": behind, "ahead": ahead, "subjects": subjects, "dirty": dirty}


def update():
    """Fast-forward the checkout to origin/BRANCH. -> (ok: bool, message: str).

    --ff-only means a checkout with conflicting local edits or unpushed
    commits is left untouched, with the reason in the message.
    """
    if not available():
        return False, "not a git checkout"
    pull = _git("pull", "--ff-only", "origin", BRANCH, timeout=60)
    if pull is None:
        return False, "git pull timed out"
    out = (pull.stdout + pull.stderr).strip()
    if pull.returncode == 0:
        return True, out or "updated"
    return False, out or "git pull failed"
