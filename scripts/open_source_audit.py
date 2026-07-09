#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conservative preflight scan before publishing the repo."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRIVATE_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"/www/wwwroot/"),
    re.compile(r"/opt/secrets/"),
    re.compile(r"alex[0-9]{5,}", re.IGNORECASE),
    re.compile(r"\b(?:TELEGRAM_HOME_CHANNEL|BAIDU_PUSH_TOKEN|HOTSPOT_BAIDU_PUSH_TOKEN|GITHUB_TOKEN|GH_TOKEN|OPENAI_API_KEY)\s*=\s*[^#\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"BEGIN (?:RSA|OPENSSH|EC|PRIVATE) KEY"),
]
IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")

GENERATED_PREFIXES = (
    "output/",
    "hot/",
    "daily/",
    "weekly/",
    "topics/",
    "analysis/",
    "sports-profiles/",
    "embed/",
    "logs/",
    "distribution/",
    "sources/snapshots/",
    "sources/source_radar_cache/",
)

GENERATED_ROOT_SUFFIXES = (
    ".html",
    ".xml",
)

ALLOWLIST = {
    ".env.example",
    "OPEN_SOURCE_RELEASE.md",
    "README.md",
    "requirements.txt",
    "LICENSE",
    "docs/schema.md",
    "sources/sample_items.json",
    "deploy/feedback.service.example",
    "scripts/open_source_audit.py",
}


def git_files(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git command failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def candidate_files() -> list[str]:
    tracked = git_files(["ls-files"])
    untracked = git_files(["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked))


def is_generated_path(path: str) -> bool:
    if path in ALLOWLIST:
        return False
    if path.startswith(GENERATED_PREFIXES):
        return True
    if "/" not in path and path.endswith(GENERATED_ROOT_SUFFIXES):
        return True
    if path in {
        "feed.xml",
        "sitemap.txt",
        "robots.txt",
        "llms.txt",
        "ai-context.txt",
        "site.webmanifest",
        "sw.js",
        "search-console-priority-urls.txt",
        "indexnow-key.txt",
        "AGENTS.md",
    }:
        return True
    if path.startswith("deploy/") and not path.endswith(".example"):
        return True
    return False


def scan_file(path: str) -> list[str]:
    if path in ALLOWLIST:
        return []
    full = ROOT / path
    if not full.is_file() or full.stat().st_size > 2_000_000:
        return []
    try:
        text = full.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings = []
    for pattern in PRIVATE_PATTERNS:
        if pattern.search(text):
            findings.append(pattern.pattern)
    for ip in IP_RE.findall(text):
        if ip.startswith("127.") or ip == "0.0.0.0":
            continue
        findings.append(f"external_ip:{ip}")
    return findings


def main() -> int:
    files = candidate_files()
    generated = [path for path in files if is_generated_path(path)]
    private_hits = []
    for path in files:
        if is_generated_path(path):
            continue
        hits = scan_file(path)
        if hits:
            private_hits.append((path, hits))

    if generated:
        print("Generated/private paths still visible to git:")
        for path in generated[:80]:
            print(f"  - {path}")
        if len(generated) > 80:
            print(f"  ... {len(generated) - 80} more")
    if private_hits:
        print("\nPotential private values in publishable files:")
        for path, hits in private_hits:
            print(f"  - {path}: {', '.join(hits)}")

    if generated or private_hits:
        return 1
    print("open-source audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
