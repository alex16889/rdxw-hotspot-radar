#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submit changed RDXW URLs to IndexNow.

Reads the generated sitemap, verifies the public key file, and posts only new or
due-for-resubmission URLs. This keeps cron submissions useful without repeatedly
submitting the same URL every few hours.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
DEFAULT_KEY_FILE = "indexnow-key.txt"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify IndexNow about changed sitemap URLs.")
    parser.add_argument("--site-root", default=".", help="Generated static site root")
    parser.add_argument("--sitemap", default="sitemap.xml", help="Sitemap index or urlset path")
    parser.add_argument("--key-file", default=DEFAULT_KEY_FILE, help="Public IndexNow key file")
    parser.add_argument("--state", default="logs/indexnow_state.json", help="Submission state JSON")
    parser.add_argument("--endpoint", default=os.environ.get("HOTSPOT_INDEXNOW_ENDPOINTS", DEFAULT_ENDPOINT), help="Comma-separated IndexNow endpoints")
    parser.add_argument("--host", default="rdxw.cc", help="Host submitted to IndexNow")
    parser.add_argument("--site-url", default=os.environ.get("HOTSPOT_SITE_URL", "https://rdxw.cc").rstrip("/"), help="Canonical site URL")
    parser.add_argument("--min-resubmit-hours", type=float, default=float(os.environ.get("HOTSPOT_INDEXNOW_MIN_RESUBMIT_HOURS", "24")), help="Minimum hours before resubmitting a changed URL")
    parser.add_argument("--limit", type=int, default=int(os.environ.get("HOTSPOT_INDEXNOW_MAX_URLS", "10000")), help="Maximum URLs per run")
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("HOTSPOT_INDEXNOW_TIMEOUT", "20")), help="Request timeout seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print candidate URLs without submitting")
    parser.add_argument("--force", action="store_true", help="Submit all sitemap URLs")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_xml(path: Path) -> ET.Element:
    return ET.fromstring(path.read_text(encoding="utf-8"))


def sitemap_child_path(site_root: Path, loc: str) -> Path:
    parsed = urlparse(loc)
    if parsed.scheme and parsed.netloc:
        return site_root / parsed.path.lstrip("/")
    return site_root / loc.lstrip("/")


def sitemap_urls(site_root: Path, sitemap_path: Path) -> list[str]:
    root = read_xml(sitemap_path)
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "sitemapindex":
        urls: list[str] = []
        for node in root.findall("sm:sitemap", SITEMAP_NS):
            loc = (node.findtext("sm:loc", namespaces=SITEMAP_NS) or "").strip()
            if not loc:
                continue
            child = sitemap_child_path(site_root, loc)
            if child.exists():
                urls.extend(sitemap_urls(site_root, child))
        return urls
    if tag == "urlset":
        return [
            (node.findtext("sm:loc", namespaces=SITEMAP_NS) or "").strip()
            for node in root.findall("sm:url", SITEMAP_NS)
            if (node.findtext("sm:loc", namespaces=SITEMAP_NS) or "").strip()
        ]
    return []


def local_file_for_url(site_root: Path, site_url: str, url: str) -> Path | None:
    parsed_site = urlparse(site_url)
    parsed_url = urlparse(url)
    if parsed_url.netloc != parsed_site.netloc:
        return None
    rel = parsed_url.path.lstrip("/")
    if not rel:
        rel = "index.html"
    elif rel.endswith("/"):
        rel += "index.html"
    return site_root / rel


def file_hash(path: Path | None) -> str:
    if not path or not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def due_urls(site_root: Path, site_url: str, urls: list[str], state: dict, min_seconds: float, force: bool, limit: int) -> tuple[list[str], dict]:
    now = time.time()
    current: dict[str, dict[str, object]] = {}
    candidates: list[str] = []
    old_urls = state.get("urls") if isinstance(state.get("urls"), dict) else {}
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        path = local_file_for_url(site_root, site_url, url)
        digest = file_hash(path)
        previous = old_urls.get(url, {}) if isinstance(old_urls.get(url), dict) else {}
        last_submitted = float(previous.get("last_submitted_at") or 0)
        submitted_hash = str(previous.get("submitted_hash") or "")
        should_submit = force or not last_submitted or (digest and digest != submitted_hash and now - last_submitted >= min_seconds)
        current[url] = {
            "seen_hash": digest,
            "submitted_hash": submitted_hash,
            "last_submitted_at": last_submitted,
            "last_seen_at": now,
        }
        if should_submit:
            candidates.append(url)
            if len(candidates) >= limit:
                break
    return candidates, current


def submit_indexnow(endpoint: str, host: str, key: str, key_location: str, urls: list[str], timeout: float) -> int:
    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": urls,
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(endpoint, data=data, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return int(response.status)


def main() -> int:
    args = parse_args()
    site_root = Path(args.site_root).resolve()
    sitemap_path = (site_root / args.sitemap).resolve()
    key_path = (site_root / args.key_file).resolve()
    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = site_root / state_path
    key = key_path.read_text(encoding="utf-8").strip()
    urls = [url for url in sitemap_urls(site_root, sitemap_path) if urlparse(url).netloc == args.host]
    state = load_json(state_path)
    candidates, current = due_urls(site_root, args.site_url, urls, state, args.min_resubmit_hours * 3600, args.force, args.limit)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "candidate_count": len(candidates), "urls": candidates}, ensure_ascii=False, indent=2))
        return 0
    if not candidates:
        save_json(state_path, {"updated_at": datetime.now(timezone.utc).isoformat(), "urls": current, "last_result": "skip_no_candidates"})
        print("skip: no IndexNow URLs due")
        return 0
    endpoints = [row.strip() for row in str(args.endpoint).split(",") if row.strip()]
    key_location = f"{args.site_url}/{args.key_file}"
    statuses = []
    for endpoint in endpoints:
        status = submit_indexnow(endpoint, args.host, key, key_location, candidates, args.timeout)
        statuses.append({"endpoint": endpoint, "status": status})
        if status not in (200, 202):
            raise SystemExit(f"IndexNow submission failed: {endpoint} returned {status}")
    now = time.time()
    for url in candidates:
        row = current.setdefault(url, {})
        row["submitted_hash"] = row.get("seen_hash") or ""
        row["last_submitted_at"] = now
        row["last_status"] = statuses[-1]["status"] if statuses else None
    save_json(
        state_path,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "host": args.host,
            "endpoint_statuses": statuses,
            "submitted_count": len(candidates),
            "urls": current,
        },
    )
    print(json.dumps({"submitted_count": len(candidates), "endpoint_statuses": statuses}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
