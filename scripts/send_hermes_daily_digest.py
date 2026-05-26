#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send a concise RDXW daily digest to a private Telegram channel.

The public site already writes output/latest_daily_brief.json. This script
turns that artifact into a shorter "DailyBrief-style" private push and gates
delivery so the 3-hour cron can run safely without spamming.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_SITE_URL = "https://rdxw.cc"
TELEGRAM_MAX_CHARS = 3900


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send RDXW daily digest to Telegram.")
    parser.add_argument("--brief", default="output/latest_daily_brief.json", help="Daily brief JSON path")
    parser.add_argument("--source-radar", default="output/source_radar.json", help="Source radar JSON path")
    parser.add_argument("--health", default="output/health.json", help="Health JSON path")
    parser.add_argument("--state", default="logs/hermes_daily_digest_state.json", help="Dedupe state path")
    parser.add_argument("--output", default="output/latest_hermes_daily_digest.json", help="Rendered digest JSON path")
    parser.add_argument(
        "--min-hour",
        type=int,
        default=int(os.environ.get("HOTSPOT_DAILY_DIGEST_MIN_HOUR") or os.environ.get("HOTSPOT_HERMES_DIGEST_MIN_HOUR", "8")),
        help="Earliest local hour allowed to send",
    )
    parser.add_argument("--force", action="store_true", help="Send even if today's digest was already sent")
    parser.add_argument("--dry-run", action="store_true", help="Build and print the digest without sending")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_run_date(value: object) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return text[:10] if text else datetime.now().strftime("%Y-%m-%d")


def clamp_line(text: object, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def strip_angle_prefix(text: object) -> str:
    value = str(text or "").strip()
    return value.removeprefix("切口：").strip()


def clean_creator_angle(title: object, angle: object, section: object) -> str:
    title_text = str(title or "")
    angle_text = strip_angle_prefix(angle)
    section_text = str(section or "")
    if not angle_text:
        return ""
    if "阿森纳进决赛和马竞出局" in angle_text and not any(word in title_text for word in ("阿森纳", "马竞", "欧冠")):
        return "抓比分转折、关键球员和下一场对阵，做一条赛后复盘主线。"
    if "明星选手个人选择" in angle_text and not any(word in title_text for word in ("Gumayusi", "HLE", "结婚")):
        return "围绕选手、战队、版本和赛果拆，优先找社区真正会讨论的点。"
    if section_text in {"X", "YouTube"} and "不要直接搬平台标题" in angle_text:
        return "提炼核心观点、评论区分歧和可二次创作的信息点。"
    return angle_text


def compact_score(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def digest_fingerprint(payload: dict[str, object]) -> str:
    raw = json.dumps(
        {
            "date": payload.get("date"),
            "brief_reference_time": payload.get("brief_reference_time"),
            "items": [
                {"title": item.get("title"), "url": item.get("url")}
                for item in payload.get("lead_items", [])
                if isinstance(item, dict)
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def source_radar_summary(source_radar: dict[str, object]) -> dict[str, object]:
    sources = [row for row in source_radar.get("sources") or [] if isinstance(row, dict)]
    ok_count = source_radar.get("ok_count")
    if ok_count in (None, ""):
        ok_count = sum(1 for row in sources if str(row.get("status") or "").lower() in {"success", "cache"})
    total = source_radar.get("source_count") or len(sources)
    names = []
    stale = []
    for row in sources[:8]:
        label = str(row.get("label") or row.get("name") or row.get("id") or "").strip()
        if label:
            names.append(label)
        status = str(row.get("status") or "").lower()
        if status and status not in {"success", "cache"} and label:
            stale.append(label)
    return {
        "ok_count": ok_count or 0,
        "source_count": total or 0,
        "names": names,
        "problem_sources": stale,
    }


def choose_lead_items(sections: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    lead_items: list[dict[str, object]] = []
    backup_items: list[dict[str, object]] = []
    for section in sections:
        items = [item for item in section.get("items") or [] if isinstance(item, dict)]
        if not items:
            continue
        first = dict(items[0])
        first["section_label"] = section.get("label") or first.get("section_label") or section.get("key")
        lead_items.append(first)
        if len(items) > 1:
            second = dict(items[1])
            second["section_label"] = section.get("label") or second.get("section_label") or section.get("key")
            backup_items.append(second)
    lead_items.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return lead_items, backup_items


def build_digest_payload(
    brief: dict[str, object],
    source_radar: dict[str, object],
    health: dict[str, object],
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or datetime.now()
    run_date = normalize_run_date(brief.get("run_date") or brief.get("date") or health.get("run_date"))
    sections = [row for row in brief.get("sections") or [] if isinstance(row, dict)]
    lead_items, backup_items = choose_lead_items(sections)
    radar = source_radar_summary(source_radar)
    site_url = str(brief.get("site_url") or health.get("site_url") or DEFAULT_SITE_URL).rstrip("/")
    health_ok = bool(health.get("ok", True))
    ranked_total = health.get("ranked_total") or len(brief.get("items") or [])
    top_titles = "、".join(clamp_line(item.get("title"), 28) for item in lead_items[:3])

    lines = [
        f"RDXW 每日简报｜{run_date}",
        "",
        f"一句话：今日优先看 {top_titles or '全站热点变化'}。",
        (
            f"概况：主榜 {ranked_total} 条；来源雷达 "
            f"{radar['ok_count']}/{radar['source_count']}；系统{'正常' if health_ok else '有异常'}。"
        ),
        "",
        "今日先看",
    ]

    for idx, item in enumerate(lead_items[:6], 1):
        section = str(item.get("section_label") or item.get("category") or item.get("section") or "").strip()
        source = str(item.get("source") or "").strip()
        score = compact_score(item.get("score"))
        meta = "｜".join(part for part in (section, source, score) if part)
        lines.append(f"{idx}. {clamp_line(item.get('title'), 56)}")
        if meta:
            lines.append(f"   {meta}")
        summary = clamp_line(item.get("summary"), 92)
        if summary:
            lines.append(f"   摘要：{summary}")
        angle = clamp_line(clean_creator_angle(item.get("title"), item.get("creator_angle"), section), 92)
        if angle:
            lines.append(f"   切口：{angle}")
        url = str(item.get("url") or "").strip()
        if url:
            lines.append(f"   详情：{url}")

    if backup_items:
        lines.extend(["", "备选池"])
        for item in backup_items[:6]:
            section = str(item.get("section_label") or item.get("category") or item.get("section") or "").strip()
            lines.append(f"- {section}：{clamp_line(item.get('title'), 52)}")

    radar_names = "、".join(radar["names"][:8])
    lines.extend(["", "来源雷达", f"- 已接入：{radar_names or '暂无来源摘要'}"])
    if radar["problem_sources"]:
        lines.append(f"- 需检查：{'、'.join(radar['problem_sources'][:5])}")
    warnings = [str(value) for value in health.get("warnings") or [] if value]
    if warnings:
        lines.append(f"- 健康提醒：{'; '.join(warnings[:3])}")
    lines.append(f"- 首页：{site_url}/")

    text = "\n".join(lines).strip()
    if len(text) > TELEGRAM_MAX_CHARS:
        text = text[: TELEGRAM_MAX_CHARS - 20].rstrip() + "\n...（已截断）"

    return {
        "ok": True,
        "date": run_date,
        "generated_at": now.isoformat(),
        "brief_reference_time": brief.get("reference_time") or brief.get("generated_at"),
        "source": "sports-hotspot-dashboard",
        "site_url": site_url,
        "lead_items": lead_items[:6],
        "backup_items": backup_items[:6],
        "source_radar": radar,
        "health": {
            "ok": health_ok,
            "ranked_total": ranked_total,
            "warnings": warnings,
        },
        "text": text,
    }


def should_send_digest(
    payload: dict[str, object],
    state: dict[str, object],
    now: datetime,
    min_hour: int,
    force: bool,
) -> tuple[bool, str]:
    if force:
        return True, "force"
    if now.hour < min_hour:
        return False, f"before_min_hour:{now.hour}<{min_hour}"
    run_date = str(payload.get("date") or "")
    if state.get("last_sent_date") == run_date:
        return False, "already_sent_today"
    return True, "ready"


def send_telegram(text: str) -> None:
    token = (
        os.environ.get("HOTSPOT_HERMES_TELEGRAM_BOT_TOKEN")
        or os.environ.get("HOTSPOT_DAILY_DIGEST_TELEGRAM_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
    )
    chat_id = (
        os.environ.get("HOTSPOT_HERMES_TELEGRAM_CHAT_ID")
        or os.environ.get("HOTSPOT_DAILY_DIGEST_TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_HOME_CHANNEL")
    )
    if not token or not chat_id:
        raise RuntimeError("missing Telegram token/chat id for daily digest")
    data = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=float(os.environ.get("HOTSPOT_HERMES_DIGEST_TIMEOUT", "15"))) as response:
        if response.status >= 400:
            raise RuntimeError(f"telegram send failed: {response.status}")


def main() -> int:
    args = parse_args()
    now = datetime.now()
    brief = load_json(Path(args.brief))
    if not brief:
        raise SystemExit(f"missing or invalid daily brief: {args.brief}")
    payload = build_digest_payload(
        brief=brief,
        source_radar=load_json(Path(args.source_radar)),
        health=load_json(Path(args.health)),
        now=now,
    )
    output_path = Path(args.output)
    write_json(output_path, payload)

    if args.dry_run:
        print(payload["text"])
        return 0

    state_path = Path(args.state)
    state = load_json(state_path)
    ok_to_send, reason = should_send_digest(payload, state, now, args.min_hour, args.force)
    if not ok_to_send:
        print(f"skip: {reason}")
        return 0

    send_telegram(str(payload["text"]))
    state.update(
        {
            "last_sent_date": payload["date"],
            "last_sent_at": time.time(),
            "fingerprint": digest_fingerprint(payload),
            "output": str(output_path),
        }
    )
    write_json(state_path, state)
    print(f"sent hermes daily digest: {payload['date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
