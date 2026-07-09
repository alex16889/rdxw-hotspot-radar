#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small local feedback receiver for a static hotspot site.

The service listens on localhost only and stores submissions as JSON Lines.
Nginx exposes it through /api/feedback.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_BODY_BYTES = 16 * 1024
MAX_MESSAGE_CHARS = 3000
MAX_FIELD_CHARS = 500
RATE_WINDOW_SECONDS = 60
RATE_MAX_PER_WINDOW = 5
RATE_BUCKET: dict[str, list[float]] = {}


def brand_name() -> str:
    return os.environ.get("HOTSPOT_BRAND_NAME", "RDXW").strip() or "RDXW"


def allowed_origins() -> set[str]:
    raw = os.environ.get("HOTSPOT_FEEDBACK_ALLOWED_ORIGINS", "").strip()
    if raw:
        return {value.strip().rstrip("/") for value in raw.split(",") if value.strip()}
    site_url = os.environ.get("HOTSPOT_SITE_URL", "https://rdxw.cc").strip().rstrip("/")
    origins = {site_url}
    parsed = urlparse(site_url)
    if parsed.scheme and parsed.netloc and not parsed.netloc.startswith("www."):
        origins.add(f"{parsed.scheme}://www.{parsed.netloc}")
    return origins


def clamp_text(value: object, limit: int) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = text.strip()
    if len(text) > limit:
        text = text[:limit].rstrip()
    return text


def client_ip(headers: object, fallback: str) -> str:
    forwarded = ""
    try:
        forwarded = str(headers.get("X-Forwarded-For") or "")
    except AttributeError:
        forwarded = ""
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or fallback
    try:
        real_ip = str(headers.get("X-Real-IP") or "").strip()
    except AttributeError:
        real_ip = ""
    return real_ip or fallback


def same_site_allowed(headers: object) -> bool:
    origins = allowed_origins()
    origin = str(headers.get("Origin") or "").strip()
    if origin:
        return origin.rstrip("/") in origins
    referer = str(headers.get("Referer") or "").strip()
    if referer:
        parsed = urlparse(referer)
        return f"{parsed.scheme}://{parsed.netloc}" in origins
    return True


def rate_limited(ip: str) -> bool:
    now = time.time()
    bucket = [ts for ts in RATE_BUCKET.get(ip, []) if now - ts < RATE_WINDOW_SECONDS]
    if len(bucket) >= RATE_MAX_PER_WINDOW:
        RATE_BUCKET[ip] = bucket
        return True
    bucket.append(now)
    RATE_BUCKET[ip] = bucket
    return False


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, object]) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Robots-Tag", "noindex")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def telegram_chat_configured() -> bool:
    token = os.environ.get("HOTSPOT_FEEDBACK_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("HOTSPOT_FEEDBACK_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_HOME_CHANNEL")
    return bool(token and chat_id)


def build_feedback_notification(entry: dict[str, object]) -> str:
    message = clamp_text(entry.get("message"), 800)
    url = clamp_text(entry.get("url"), 300) or clamp_text(entry.get("page"), 300)
    contact = clamp_text(entry.get("contact"), 160) or "未填"
    feedback_type = clamp_text(entry.get("type"), 80) or "其他"
    created_at = clamp_text(entry.get("created_at"), 80)
    lines = [
        f"{brand_name()} 新反馈",
        f"类型：{feedback_type}",
        f"时间：{created_at}",
        f"页面：{url or '未填'}",
        f"联系方式：{contact}",
        "",
        message,
    ]
    return "\n".join(lines)


def send_feedback_notification(entry: dict[str, object]) -> None:
    if os.environ.get("HOTSPOT_FEEDBACK_NOTIFY_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    token = os.environ.get("HOTSPOT_FEEDBACK_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("HOTSPOT_FEEDBACK_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return
    data = json.dumps(
        {
            "chat_id": chat_id,
            "text": build_feedback_notification(entry),
            "disable_web_page_preview": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=float(os.environ.get("HOTSPOT_FEEDBACK_NOTIFY_TIMEOUT", "8"))) as response:
        if response.status >= 400:
            raise RuntimeError(f"telegram notification failed: {response.status}")


class FeedbackHandler(BaseHTTPRequestHandler):
    server_version = "RDXWFeedback/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(self, HTTPStatus.OK, {"ok": True})
            return
        json_response(self, HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "method_not_allowed"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/feedback":
            json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not same_site_allowed(self.headers):
            json_response(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": "bad_origin"})
            return
        ip = client_ip(self.headers, self.client_address[0])
        if rate_limited(ip):
            json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": "rate_limited"})
            return
        try:
            content_length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "bad_size"})
            return
        try:
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "bad_json"})
            return
        if not isinstance(payload, dict):
            json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "bad_payload"})
            return
        if clamp_text(payload.get("company"), 80):
            json_response(self, HTTPStatus.OK, {"ok": True, "ignored": True})
            return
        message = clamp_text(payload.get("message"), MAX_MESSAGE_CHARS)
        feedback_type = clamp_text(payload.get("type"), 80)
        if len(message) < 5:
            json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "message_too_short"})
            return
        entry = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": feedback_type or "其他",
            "url": clamp_text(payload.get("url"), MAX_FIELD_CHARS),
            "message": message,
            "contact": clamp_text(payload.get("contact"), MAX_FIELD_CHARS),
            "page": clamp_text(payload.get("page"), MAX_FIELD_CHARS),
            "user_agent": clamp_text(self.headers.get("User-Agent"), 300),
            "ip": ip,
        }
        store_path = Path(self.server.store_path)  # type: ignore[attr-defined]
        store_path.parent.mkdir(parents=True, exist_ok=True)
        with store_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        try:
            send_feedback_notification(entry)
        except Exception as exc:
            if os.environ.get("RDXW_FEEDBACK_DEBUG"):
                print(f"feedback notification failed: {exc}", flush=True)
        json_response(self, HTTPStatus.OK, {"ok": True})

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("RDXW_FEEDBACK_DEBUG"):
            super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18088)
    parser.add_argument("--store", default="/var/lib/rdxw-feedback/feedback.jsonl")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), FeedbackHandler)
    server.store_path = args.store  # type: ignore[attr-defined]
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
