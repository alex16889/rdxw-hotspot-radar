#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send Telegram alerts when RDXW hotspot health is abnormal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify hotspot health warnings to Telegram.")
    parser.add_argument("--health", default="output/health.json", help="Path to health.json")
    parser.add_argument("--state", default="logs/health_alert_state.json", help="Alert dedupe state path")
    parser.add_argument("--force", action="store_true", help="Send even when health is OK")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def alert_fingerprint(health: dict) -> str:
    payload = {
        "ok": health.get("ok"),
        "warnings": health.get("warnings") or [],
        "query_error_count": health.get("query_error_count") or 0,
        "source_radar_failed_count": health.get("source_radar_failed_count") or 0,
        "llm_errors": ((health.get("llm_editorial") or {}).get("errors") or []),
        "llm_degraded_reason": ((health.get("llm_editorial") or {}).get("degraded_reason") or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def should_send(health: dict, state: dict, force: bool) -> bool:
    if force:
        return True
    abnormal = not bool(health.get("ok")) or bool(health.get("warnings"))
    if not abnormal:
        return False
    fingerprint = alert_fingerprint(health)
    repeat_minutes = int(os.environ.get("HOTSPOT_ALERT_REPEAT_MINUTES", "180"))
    last_sent = float(state.get("last_sent_at") or 0)
    if state.get("fingerprint") == fingerprint and time.time() - last_sent < repeat_minutes * 60:
        return False
    return True


def build_message(health: dict, force: bool) -> str:
    warnings = health.get("warnings") or []
    llm = health.get("llm_editorial") or {}
    status = "正常" if health.get("ok") and not warnings else "异常"
    lines = [
        f"RDXW 热点雷达健康检查｜{status}",
        f"日期：{health.get('run_date') or ''}",
        f"主榜：{health.get('ranked_total') or 0} 条；来源雷达：{health.get('source_radar_ok_count') or 0} 成功 / {health.get('source_radar_failed_count') or 0} 失败",
        f"LLM：{'启用' if llm.get('enabled') else '未启用'}，已增强 {llm.get('applied') or 0} 条",
    ]
    if llm.get("enabled") and not llm.get("live_enabled", True):
        lines.append("LLM模式：缓存/规则兜底，未发起实时请求")
    elif llm.get("degraded_reason"):
        lines.append(f"LLM降级：{llm.get('degraded_reason')}")
    if warnings:
        lines.append("警告：")
        lines.extend(f"- {warning}" for warning in warnings[:8])
    if llm.get("errors"):
        lines.append("LLM错误：")
        lines.extend(f"- {error}" for error in llm.get("errors", [])[:3])
    lines.append(f"Health：{health.get('site_url', 'https://rdxw.cc')}/output/health.json")
    if force and not warnings:
        lines.append("说明：本次为 force 测试推送。")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ.get("HOTSPOT_ALERT_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("HOTSPOT_ALERT_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        print("skip: missing TELEGRAM_BOT_TOKEN or TELEGRAM_HOME_CHANNEL")
        return
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()
    print("sent telegram alert")


def main() -> int:
    args = parse_args()
    health_path = Path(args.health)
    state_path = Path(args.state)
    health = load_json(health_path)
    if not health:
        health = {"ok": False, "warnings": [f"health 文件不可读：{health_path}"]}
    state = load_json(state_path)
    if not should_send(health, state, args.force):
        print("skip: no alert needed")
        return 0
    send_telegram(build_message(health, args.force))
    save_json(state_path, {"fingerprint": alert_fingerprint(health), "last_sent_at": time.time()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
