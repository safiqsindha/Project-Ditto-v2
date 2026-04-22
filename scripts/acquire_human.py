#!/usr/bin/env python3
"""
Acquire human-AI collaborative session trajectories from SpecStory files
committed to public GitHub repositories.

Methodology based on: "Programming by Chat: A Large-Scale Behavioral Analysis of
11,579 Real-World AI-Assisted IDE Sessions" (arXiv 2604.00436, March 2026).
SpecStory (https://specstory.com) auto-saves AI coding sessions to
.specstory/history/ within developer repositories.

Usage
-----
    export GITHUB_TOKEN=ghp_...
    python scripts/acquire_human.py \\
        --target 200 \\
        --out data/human_sessions/ \\
        --start-month 2024-09 \\
        --end-month 2026-04

Requirements
------------
    GITHUB_TOKEN environment variable (or --github-token flag)
    Required scopes: public_repo (read-only)

Data pipeline
-------------
1. GitHub Code Search API (date-prefix partitioned, 100 results/page)
2. GitHub Git Blobs API (fetch raw file content)
3. Secret / PII detection (reject if unredactable secrets found)
4. License filter (accept MIT / Apache-2.0 / BSD / ISC / Unlicense / CC0)
5. Markdown parser → TrajectoryLog
6. Min-event filter (≥ 15 turns)
7. Deduplicate by content SHA

Gate 2c check
-------------
Exits with code 1 if < --gate-threshold usable sessions are acquired
(default: 100 minimum, spec §5 Gate 2c).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser_human import (
    filter_trajectory,
    parse_human_session,
    detect_secrets,
    redact_emails,
    TrajectoryLog,
)


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

class GitHubClient:
    """Minimal GitHub API client using urllib (no extra dependencies)."""

    BASE = "https://api.github.com"
    SEARCH_DELAY = 2.2   # seconds between search requests (GitHub: 30/min authenticated)
    FETCH_DELAY  = 0.5   # seconds between blob/repo fetches

    def __init__(self, token: str, cache_dir: Path):
        self.token = token
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._repo_license_cache: dict[str, str | None] = {}

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-ditto-v2/1.0",
        }

    def _get(self, url: str, cache_key: str | None = None) -> dict | None:
        """GET a URL, with optional file-based caching."""
        if cache_key:
            cache_file = self.cache_dir / f"{cache_key}.json"
            if cache_file.exists():
                with cache_file.open() as f:
                    return json.load(f)

        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 403:
                # Rate limited — wait and retry once
                reset = int(e.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(0, reset - time.time()) + 5
                print(f"  Rate limited; sleeping {wait:.0f}s …", file=sys.stderr)
                time.sleep(wait)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
            elif e.code in (404, 422, 451):
                return None
            else:
                raise
        except urllib.error.URLError:
            return None

        if cache_key:
            cache_file = self.cache_dir / f"{cache_key}.json"
            with cache_file.open("w") as f:
                json.dump(data, f)
        return data

    def search_code(self, query: str, page: int = 1) -> dict | None:
        """Search GitHub code index."""
        q = urllib.parse.quote(query) if hasattr(urllib, 'parse') else query.replace(' ', '+')
        url = f"{self.BASE}/search/code?q={q}&per_page=100&page={page}"
        time.sleep(self.SEARCH_DELAY)
        return self._get(url)

    def get_blob(self, owner: str, repo: str, sha: str) -> str | None:
        """Fetch decoded content of a git blob by SHA."""
        cache_key = f"blob_{sha}"
        url = f"{self.BASE}/repos/{owner}/{repo}/git/blobs/{sha}"
        time.sleep(self.FETCH_DELAY)
        data = self._get(url, cache_key=cache_key)
        if not data:
            return None
        content_b64 = data.get("content", "")
        if not content_b64:
            return None
        try:
            return base64.b64decode(content_b64.replace("\n", "")).decode("utf-8", errors="replace")
        except Exception:
            return None

    def get_repo_license(self, owner: str, repo: str) -> str | None:
        """Return the SPDX license ID for a repo, or None if unlicensed."""
        full_name = f"{owner}/{repo}"
        if full_name in self._repo_license_cache:
            return self._repo_license_cache[full_name]

        cache_key = f"repo_{owner}_{repo}"
        url = f"{self.BASE}/repos/{owner}/{repo}"
        time.sleep(self.FETCH_DELAY)
        data = self._get(url, cache_key=cache_key)
        spdx = None
        if data and data.get("license"):
            spdx = data["license"].get("spdx_id")
        self._repo_license_cache[full_name] = spdx
        return spdx


import re
import urllib.parse

# ---------------------------------------------------------------------------
# License filter
# ---------------------------------------------------------------------------

_ACCEPTABLE_LICENSES = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "ISC", "Unlicense", "CC0-1.0",
    "MPL-2.0",           # copyleft only applies to modifications of source files
    "LGPL-2.0-only", "LGPL-2.0-or-later",
    "LGPL-2.1-only", "LGPL-2.1-or-later",
    "LGPL-3.0-only", "LGPL-3.0-or-later",
})


def is_acceptable_license(spdx_id: str | None) -> bool:
    if spdx_id is None:
        return False
    return spdx_id in _ACCEPTABLE_LICENSES


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _log_to_dict(log: TrajectoryLog) -> dict:
    return {
        "task_id": log.task_id,
        "model": log.model,
        "agent": log.agent,
        "outcome": log.outcome,
        "source": log.source,
        "events": [
            {"type": e.type, "step": e.step, "args": e.args}
            for e in log.events
        ],
    }


# ---------------------------------------------------------------------------
# Main acquisition loop
# ---------------------------------------------------------------------------

def _month_range(start: str, end: str) -> list[str]:
    """Return list of YYYY-MM strings from start to end (inclusive)."""
    from datetime import date
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]),   int(end[5:7])
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire SpecStory human-AI sessions from GitHub"
    )
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"),
                        help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--out", default="data/human_sessions/",
                        help="Output directory (default: data/human_sessions/)")
    parser.add_argument("--target", type=int, default=200,
                        help="Maximum sessions to save (default: 200)")
    parser.add_argument("--gate-threshold", type=int, default=100,
                        help="Minimum for Gate 2c (default: 100)")
    parser.add_argument("--min-events", type=int, default=15,
                        help="Minimum events per trajectory (default: 15)")
    parser.add_argument("--start-month", default="2024-09",
                        help="Earliest month to search (YYYY-MM, default: 2024-09)")
    parser.add_argument("--end-month", default="2026-04",
                        help="Latest month to search (YYYY-MM, default: 2026-04)")
    parser.add_argument("--cache-dir", default=".cache/acquire_human",
                        help="Directory for caching API responses")
    args = parser.parse_args()

    if not args.github_token:
        print("ERROR: GitHub token required.  Set GITHUB_TOKEN or use --github-token.",
              file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir)

    client = GitHubClient(args.github_token, cache_dir)

    months = _month_range(args.start_month, args.end_month)
    print(f"Searching {len(months)} monthly partitions "
          f"({args.start_month} → {args.end_month})")

    usable: list[TrajectoryLog] = []
    seen_shas: set[str] = set()
    rejection_log: list[dict] = []

    stats = {
        "candidates": 0,
        "secret_rejected": 0,
        "license_rejected": 0,
        "parse_errors": 0,
        "too_short": 0,
        "duplicate": 0,
        "accepted": 0,
    }

    for month in months:
        if len(usable) >= args.target:
            break

        query = f"path:.specstory/history filename:{month} extension:md"
        print(f"  Searching {month} …", end=" ", flush=True)

        page = 1
        page_items = []
        while True:
            result = client.search_code(query, page=page)
            if not result or "items" not in result:
                break
            items = result["items"]
            if not items:
                break
            page_items.extend(items)
            if len(items) < 100 or page >= 10:
                break
            page += 1

        print(f"{len(page_items)} candidates")
        stats["candidates"] += len(page_items)

        for item in page_items:
            if len(usable) >= args.target:
                break

            repo_full = item.get("repository", {}).get("full_name", "")
            if not repo_full or "/" not in repo_full:
                continue
            owner, repo = repo_full.split("/", 1)
            sha = item.get("sha", "")
            name = item.get("name", "unknown.md")

            # Duplicate check
            if sha in seen_shas:
                stats["duplicate"] += 1
                continue

            # License check
            spdx = client.get_repo_license(owner, repo)
            if not is_acceptable_license(spdx):
                stats["license_rejected"] += 1
                rejection_log.append({"sha": sha, "repo": repo_full, "reason": f"license:{spdx}"})
                continue

            # Fetch content
            content = client.get_blob(owner, repo, sha)
            if not content or len(content) < 500:
                continue

            # Secret detection
            secrets = detect_secrets(content)
            if secrets:
                stats["secret_rejected"] += 1
                rejection_log.append({"sha": sha, "repo": repo_full, "reason": f"secret:{secrets}"})
                continue

            # Redact emails
            content = redact_emails(content)

            # Parse
            session_id = name.replace(".md", "")
            raw = {"session_id": session_id, "content": content, "repo": repo_full}
            try:
                log = parse_human_session(raw)
            except (ValueError, Exception) as exc:
                stats["parse_errors"] += 1
                rejection_log.append({"sha": sha, "repo": repo_full, "reason": f"parse_error:{exc}"})
                continue

            # Event count filter
            if not filter_trajectory(log, min_events=args.min_events):
                stats["too_short"] += 1
                continue

            seen_shas.add(sha)
            usable.append(log)
            stats["accepted"] += 1

    # Write output
    out_file = out_dir / "trajectories.jsonl"
    with out_file.open("w", encoding="utf-8") as fh:
        for log in usable:
            fh.write(json.dumps(_log_to_dict(log)) + "\n")

    # Write rejection log
    rejection_file = out_dir / "rejection_log.jsonl"
    with rejection_file.open("w", encoding="utf-8") as fh:
        for entry in rejection_log:
            fh.write(json.dumps(entry) + "\n")

    print(f"\nSummary:")
    for k, v in stats.items():
        print(f"  {k:25s}: {v}")
    print(f"\n  Output file    : {out_file}")
    print(f"  Rejection log  : {rejection_file}")

    # Gate 2c check
    if len(usable) < args.gate_threshold:
        print(
            f"\nGATE 2c FAIL: {len(usable)} < {args.gate_threshold} required.  "
            "Options: extend date range, relax min-events, or escalate to human review.",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(f"\nGATE 2c PASS: {len(usable)} >= {args.gate_threshold}")


if __name__ == "__main__":
    main()
