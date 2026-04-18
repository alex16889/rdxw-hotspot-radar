#!/usr/bin/env python3
"""Export sports-only context from latest_hotspots_ranked.json.

Reads:
  output/latest_hotspots_ranked.json
Writes:
  output/latest_sports_context.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "output" / "latest_hotspots_ranked.json"
OUTPUT_PATH = ROOT / "output" / "latest_sports_context.json"

MATCH_KEYWORDS = [
    "切尔西", "曼联", "英超", "大连英博", "河南", "中超", "杜兰特", "湖人", "NBA",
    "泽林斯基", "意甲", "町田泽维亚", "吉达联合", "亚冠", "魔术", "黄蜂", "班凯罗",
    "阿尔特塔", "欧冠", "皇马", "国米", "曼城", "阿森纳", "CBA", "辽宁", "山东",
    "浙江", "吉林",
]


def load_ranked_items(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("items") or data.get("data") or []
    if isinstance(data, list):
        return data
    return []


def contains_any(text: str, words) -> bool:
    return any(w in text for w in words)


def extract_match_keywords(title: str):
    keywords = []
    for kw in MATCH_KEYWORDS:
        if kw in title and kw not in keywords:
            keywords.append(kw)

    def add_side(side: str):
        side = side.strip().strip("《》()（）[]【】").strip()
        side = re.sub(r"^(?:今晚|明晚|今天|昨日|今晚19点|今晚\d+点|解说|欢迎大伙|欢迎大家|最新|前瞻|战报|直播|赛前)[:：,，\s]*", "", side)
        side = side.strip()
        if not side:
            return
        for kw in MATCH_KEYWORDS:
            if kw in side and kw not in keywords:
                keywords.append(kw)
        if len(side) <= 8 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z·\-]+", side) and side not in keywords:
            keywords.append(side)

    m = re.search(r"(.+?)\s*(?:vs|VS|Vs)\s*(.+?)(?:[，,。：:|｜\s]|$)", title)
    if m:
        add_side(m.group(1))
        add_side(m.group(2))

    m = re.search(r"(.+?)\s*(?:对阵|大战)\s*(.+?)(?:[，,。：:|｜\s]|$)", title)
    if m:
        add_side(m.group(1))
        add_side(m.group(2))

    return keywords


def make_wechat_use(topic_type: str, title: str):
    if topic_type == "sports_preview":
        if contains_any(title, ["vs", "VS", "Vs", "对阵", "前瞻", "出战成疑", "伤停", "今晚", "明晚"]):
            return "赛前引入"
        if contains_any(title, ["选秀", "新秀"]):
            return "人物话题"
        return "赛前素材"
    if topic_type == "sports_result":
        if contains_any(title, ["晋级", "淘汰", "四强", "大胜", "轻取", "绝平", "救主", "逆转", "战报", "破门", "进球", "世界波"]):
            return "复盘素材"
        return "赛果补充"
    if topic_type == "sports_star":
        return "人物话题"
    if topic_type == "sports_low_value":
        return "不建议主推"
    return "赛前素材"


def make_betting_angle(title: str):
    if contains_any(title, ["平局", "平局最多"]):
        return "防平 / 小比分 / 谨慎看方向"
    if contains_any(title, ["出战成疑", "伤停", "复出", "缺阵"]):
        return "伤停影响盘口，不适合过早定方向"
    if contains_any(title, ["vs", "VS", "Vs", "对阵", "前瞻"]):
        return "赛前热度高，结合盘口变化再判断"
    if contains_any(title, ["晋级", "淘汰", "四强"]):
        return "更适合复盘和后续赛程关注"
    if contains_any(title, ["大胜", "轻取"]):
        return "强弱差距明显，可观察状态延续"
    if contains_any(title, ["绝平", "救主", "逆转"]):
        return "转折属性强，适合做复盘标题"
    if contains_any(title, ["破门", "进球", "世界波"]):
        return "球员状态话题，不直接作为盘口依据"
    if contains_any(title, ["选秀", "新秀"]):
        return "人物长期话题，不适合作为今日推荐依据"
    return "只作话题素材，不直接决定推荐方向"


def build_item(item):
    title = item.get("title") or ""
    topic_type = item.get("topic_type") or ""
    editor_note = item.get("editor_note") or ""
    source = item.get("source") or ""
    url = item.get("url") or ""

    out = {
        "title": title,
        "source": source,
        "url": url,
        "topic_type": topic_type,
        "score": item.get("score"),
        "editor_note": editor_note,
        "wechat_use": make_wechat_use(topic_type, title),
        "betting_angle": make_betting_angle(title),
        "match_keywords": extract_match_keywords(title),
    }

    # Keep commonly useful fields if present, but do not depend on them.
    for key in ("summary_hint", "topic", "repo", "stars", "forks", "language", "recommend_reason"):
        if key in item:
            out[key] = item.get(key)

    return out


def main() -> int:
    if not INPUT_PATH.exists():
        raise SystemExit(f"missing input: {INPUT_PATH}")

    items = load_ranked_items(INPUT_PATH)
    sports_items = [item for item in items if item.get("topic") == "sports"]
    payload_items = [build_item(item) for item in sports_items]

    payload = {
        "ok": True,
        "count": len(payload_items),
        "items": payload_items,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(OUTPUT_PATH.relative_to(ROOT)), "count": len(payload_items)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
