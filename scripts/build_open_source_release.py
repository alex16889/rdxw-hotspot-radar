#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a local preview tree for the open-source release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_git(args: list[str]) -> list[str]:
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


def release_files() -> list[str]:
    tracked = run_git(["ls-files"])
    untracked = run_git(["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_audit() -> None:
    result = subprocess.run(
        ["python3", "scripts/open_source_audit.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a local open-source release preview.")
    parser.add_argument("--output", default="dist/open-source-preview", help="Preview output directory")
    parser.add_argument("--dry-run", action="store_true", help="Only print the file list")
    parser.add_argument("--skip-audit", action="store_true", help="Do not run scripts/open_source_audit.py first")
    args = parser.parse_args()

    if not args.skip_audit:
        run_audit()

    files = release_files()
    if args.dry_run:
        for path in files:
            print(path)
        print(f"\n{len(files)} files")
        return 0

    out_dir = (ROOT / args.output).resolve()
    if out_dir == ROOT:
        raise SystemExit("refusing to write release preview over project root")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "files": [],
    }
    for rel in files:
        src = ROOT / rel
        if not src.is_file():
            continue
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest["files"].append(
            {
                "path": rel,
                "bytes": src.stat().st_size,
                "sha256": sha256(src),
            }
        )

    manifest_path = out_dir / "OPEN_SOURCE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(out_dir), "file_count": len(manifest["files"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
