#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily multi-topic hotspot runner.

- Fetches Google News RSS for sports / ai / entertainment and GitHub Search API for github
- Writes raw items with topic metadata
- Invokes transform.hotspot_pipeline for ranking + Markdown rendering

No Google Sheets, no Apps Script, no CSV/TSV exports.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests

from transform.hotspot_pipeline import build_markdown, rank_items, write_json, write_text

ROOT = Path(__file__).resolve().parent
DOMESTIC_SITE_FILTER = (
    "(site:sports.sina.com.cn OR site:sports.qq.com OR site:sports.163.com OR "
    "site:sports.cctv.com OR site:sports.people.com.cn OR site:news.sports.cn OR "
    "site:sports.sohu.com)"
)

QUERY_SPECS = [
    # sports
    {
        "topic": "sports",
        "name": "domestic_league_cn",
        "query": f"(CBA OR WCBA OR 中国女篮 OR 中国男篮 OR 中超 OR 国足 OR 足协杯) {DOMESTIC_SITE_FILTER} -site:fans.sports.qq.com when:1d",
        "required_keywords": ["CBA", "WCBA", "中国女篮", "中国男篮", "中超", "国足", "足协杯", "蓉城", "国安", "泰山", "海港"],
    },
    {
        "topic": "sports",
        "name": "national_team_cn",
        "query": f"(国乒 OR WTT OR 国羽 OR 羽毛球 OR 郑钦文 OR 张帅 OR 中国球员 OR 中国选手 OR 斯诺克) {DOMESTIC_SITE_FILTER} when:1d",
        "required_keywords": ["国乒", "WTT", "国羽", "羽毛球", "郑钦文", "张帅", "中国球员", "中国选手", "斯诺克", "太原站"],
    },
    {
        "topic": "sports",
        "name": "basketball_global_cn",
        "query": f"(NBA OR 附加赛 OR 季后赛) {DOMESTIC_SITE_FILTER} -site:fans.sports.qq.com when:1d",
        "required_keywords": ["NBA", "附加赛", "季后赛", "勇士", "湖人", "太阳", "魔术", "黄蜂"],
    },
    {
        "topic": "sports",
        "name": "football_global_cn",
        "query": f"(欧冠 OR 英超 OR 西甲 OR 意甲 OR 德甲 OR 转会) {DOMESTIC_SITE_FILTER} -site:fans.sports.qq.com when:1d",
        "required_keywords": ["欧冠", "英超", "西甲", "意甲", "德甲", "转会", "利物浦", "巴萨", "皇马", "拜仁"],
    },
    {
        "topic": "sports",
        "name": "hot_cn",
        "query": f"(绝杀 OR 逆转 OR 晋级 OR 出局 OR 无缘 OR 伤退 OR 复出 OR 官宣) {DOMESTIC_SITE_FILTER} -site:fans.sports.qq.com when:1d",
        "required_keywords": ["绝杀", "逆转", "晋级", "出局", "无缘", "伤退", "复出", "官宣"],
    },
    {
        "topic": "sports",
        "name": "global_high_value_cn",
        "query": "(NBA OR 欧冠 OR 英超 OR 意甲 OR 德甲 OR 中超 OR 亚冠 OR WTT OR 斯诺克 OR WCBA OR 女篮) (懂球帝 OR 直播吧 OR 体坛周报 OR 虎扑 OR ESPN OR Sky Sports OR Reuters OR AP OR The Athletic) when:1d",
        "required_keywords": ["NBA", "欧冠", "英超", "意甲", "德甲", "中超", "亚冠", "WTT", "斯诺克", "WCBA", "女篮"],
    },
    {
        "topic": "sports",
        "name": "global_star_cn",
        "query": "(梅西 OR C罗 OR 东契奇 OR 约基奇 OR 姆巴佩 OR Ohtani OR 球星) (懂球帝 OR ESPN OR Reuters OR AP OR The Athletic) when:1d",
        "required_keywords": ["梅西", "C罗", "东契奇", "约基奇", "姆巴佩", "Ohtani", "球星"],
    },
    {
        "topic": "sports",
        "name": "reuters_ap_cn",
        "query": "(NBA OR 欧冠 OR 英超 OR 意甲 OR 德甲 OR 中超 OR 亚冠 OR WTT OR 斯诺克 OR WCBA OR 女篮) (site:reuters.com OR site:apnews.com OR site:espn.com OR site:skysports.com OR site:theathletic.com) when:1d",
        "required_keywords": ["NBA", "欧冠", "英超", "意甲", "德甲", "中超", "亚冠", "WTT", "斯诺克", "WCBA", "女篮"],
    },
    {
        "topic": "sports",
        "name": "domestic_alt_cn",
        "query": "(NBA OR 欧冠 OR 英超 OR 意甲 OR 德甲 OR 中超 OR 亚冠 OR WTT OR 斯诺克 OR WCBA OR 女篮) (site:dongqiudi.com OR site:zhibo8.cc OR site:hu扑.com OR site:titan24.com OR site:ppsports.com) when:1d",
        "required_keywords": ["NBA", "欧冠", "英超", "意甲", "德甲", "中超", "亚冠", "WTT", "斯诺克", "WCBA", "女篮"],
    },
    {
        "topic": "sports",
        "name": "sports_media_cn",
        "query": "(NBA OR 欧冠 OR 英超 OR 意甲 OR 德甲 OR 中超 OR 亚冠 OR WTT OR 斯诺克 OR WCBA OR 女篮) (site:ppsports.com OR site:zhibo8.cc OR site:titan24.com OR site:hupu.com OR site:dongqiudi.com) when:1d",
        "required_keywords": ["NBA", "欧冠", "英超", "意甲", "德甲", "中超", "亚冠", "WTT", "斯诺克", "WCBA", "女篮"],
    },
    # ai
    {
        "topic": "ai",
        "name": "openai_ai_cn",
        "query": "OpenAI OR ChatGPT OR Gemini OR Claude OR Sora OR 英伟达 OR 人工智能 OR 大模型 when:1d",
        "required_keywords": ["OpenAI", "ChatGPT", "Gemini", "Claude", "Sora", "英伟达", "人工智能", "大模型"],
    },
    {
        "topic": "ai",
        "name": "ai_product_cn",
        "query": "AI工具 OR 大模型 OR 智能体 OR 苹果AI OR 英伟达 OR 模型更新 when:1d",
        "required_keywords": ["AI工具", "大模型", "智能体", "苹果AI", "英伟达", "模型更新"],
    },
    # entertainment
    {
        "topic": "entertainment",
        "name": "entertainment_hot_cn",
        "query": "微博热搜 OR 电影 OR 电视剧 OR 综艺 OR 明星 OR 票房 OR 演员 OR 导演 when:1d",
        "required_keywords": ["微博热搜", "电影", "电视剧", "综艺", "明星", "票房", "演员", "导演"],
    },
    {
        "topic": "entertainment",
        "name": "movie_tv_cn",
        "query": "电影 OR 电视剧 OR 综艺 OR 定档 OR 票房 OR 上映 when:1d",
        "required_keywords": ["电影", "电视剧", "综艺", "定档", "票房", "上映"],
    },
]

GOOGLE_NEWS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135 Safari/537.36",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch, rank, and export daily multi-topic hotspots.")
    parser.add_argument("--date", default=None, help="YYYYMMDD，例如 20260418；默认今天。")
    parser.add_argument("--output-dir", default="output", help="Directory for ranked outputs.")
    parser.add_argument("--sources-dir", default="sources", help="Directory for fetched raw source files.")
    parser.add_argument("--top", type=int, default=20, help="How many ranked hotspot rows to export.")
    parser.add_argument("--min-score", type=float, default=5.0, help="Minimum total_score to keep in the final export.")
    parser.add_argument(
        "--reference-time",
        help="ISO-8601 reference timestamp used for scoring. Defaults to local current time.",
    )
    return parser.parse_args()


def today_stamp() -> str:
    return dt.date.today().strftime("%Y%m%d")


def google_news_url(query: str) -> str:
    return GOOGLE_NEWS_TEMPLATE.format(query=quote_plus(query))


def parse_pubdate(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone().replace(second=0, microsecond=0).isoformat()


def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def should_skip(title: str, source: str | None) -> bool:
    if len(title.strip()) <= 4:
        return True
    if source and source.strip().lower() in {"facebook", "腾讯体育社区", "新浪网"}:
        return True
    blocked_patterns = [
        re.compile(r"^(NBA|CBA|WCBA|WTT|中超)$", re.IGNORECASE),
        re.compile(r"看NBA足球网球赛车NFL"),
        re.compile(r"社区·汇聚心跳"),
        re.compile(r"^\d{1,2}-\d{1,2}:"),
        re.compile(r"^\[[^\]]+\]"),
        re.compile(r"^\[图\]"),
        re.compile(r"\bprep talk\b", re.IGNORECASE),
        re.compile(r"\bhow to buy\b", re.IGNORECASE),
        re.compile(r"\bhow to watch\b", re.IGNORECASE),
        re.compile(r"\bwhere to watch\b", re.IGNORECASE),
        re.compile(r"\bprediction(s)?\b", re.IGNORECASE),
        re.compile(r"\bodds\b", re.IGNORECASE),
        re.compile(r"\bprop bets?\b", re.IGNORECASE),
        re.compile(r"\btickets?\b", re.IGNORECASE),
        re.compile(r"视频集锦"),
        re.compile(r"集锦"),
        re.compile(r"比赛回顾"),
        re.compile(r"回放"),
        re.compile(r"录像"),
        re.compile(r"图集"),
        re.compile(r"门票"),
        re.compile(r"赔率"),
        re.compile(r"购彩"),
        re.compile(r"直播"),
        re.compile(r"哪里看"),
        re.compile(r"免费观看"),
        re.compile(r"预测"),
        re.compile(r"胜率"),
        re.compile(r"有资格"),
        re.compile(r"有过"),
        re.compile(r"都有谁"),
        re.compile(r"还会回来吗"),
        re.compile(r"诸神黄昏"),
        re.compile(r"常胜将军"),
        re.compile(r"往年"),
        re.compile(r"历史第"),
        re.compile(r"第\d+次出现"),
        re.compile(r"明天稳了"),
        re.compile(r"ESPN", re.IGNORECASE),
    ]
    return any(pattern.search(title) for pattern in blocked_patterns)


def query_matches_title(title: str, spec: dict) -> bool:
    required_keywords = spec.get("required_keywords")
    if not isinstance(required_keywords, list) or not required_keywords:
        return True
    lowered_title = title.lower()
    return any(keyword.lower() in lowered_title for keyword in required_keywords)


def split_title(title: str, source: str | None) -> str:
    if source and title.endswith(f" - {source}"):
        return title[: -(len(source) + 3)].strip()
    return title.strip()


def text(node) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def parse_feed(xml_text: str, spec: dict) -> list[dict[str, object]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, object]] = []
    for item in root.findall("./channel/item"):
        source_el = item.find("source")
        source_name = source_el.text.strip() if source_el is not None and source_el.text else None
        title = split_title(unescape(item.findtext("title", "").strip()), source_name)
        description = text(item.find("description"))
        if not title or should_skip(title, source_name):
            continue
        if not query_matches_title(f"{title} {description}", spec):
            continue

        published_at = parse_pubdate(item.findtext("pubDate", ""))
        link = item.findtext("link", "").strip() or None
        source_url = source_el.attrib.get("url") if source_el is not None else None

        items.append(
            {
                "title": title,
                "summary": description,
                "source": source_name,
                "url": link,
                "published_at": published_at,
                "latest_published_at": published_at,
                "league": spec.get("league", ""),
                "query_name": spec["name"],
                "keyword": spec["name"],
                "query": spec["query"],
                "topic": spec["topic"],
                "required_keywords": list(spec.get("required_keywords", [])),
                "sources": [{"name": source_name, "url": source_url}] if source_name else [],
            }
        )
    return items


def fetch_query(spec: dict) -> list[dict[str, object]]:
    response = requests.get(google_news_url(spec["query"]), headers=HEADERS, timeout=20)
    response.raise_for_status()
    return parse_feed(response.text, spec)


def fetch_github_trending_like(date_stamp: str) -> list[dict[str, object]]:
    """Fetch GitHub Search API results without a token.

    date_stamp is YYYYMMDD; we use the previous 7 days for created/pushed queries.
    """

    try:
        base_date = dt.datetime.strptime(date_stamp, "%Y%m%d").date()
    except ValueError:
        base_date = dt.date.today()
    since_date = (base_date - dt.timedelta(days=7)).strftime("%Y-%m-%d")

    specs = [
        {"name": "created_stars_50", "q": f"created:>{since_date} stars:>50", "sort": "stars", "order": "desc"},
        {"name": "pushed_stars_500", "q": f"pushed:>{since_date} stars:>500", "sort": "updated", "order": "desc"},
        {"name": "topic_ai", "q": f"topic:ai stars:>100", "sort": "stars", "order": "desc"},
        {"name": "topic_agent", "q": f"topic:agent stars:>50", "sort": "stars", "order": "desc"},
        {"name": "topic_llm", "q": f"topic:llm stars:>50", "sort": "stars", "order": "desc"},
        {"name": "topic_automation", "q": f"topic:automation stars:>50", "sort": "stars", "order": "desc"},
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (GitHub hotspot runner)",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    seen = set()
    items: list[dict[str, object]] = []
    for spec in specs:
        params = {
            "q": spec["q"],
            "sort": spec["sort"],
            "order": spec["order"],
            "per_page": 20,
        }
        try:
            response = requests.get("https://api.github.com/search/repositories", params=params, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] github fetch failed name={spec['name']} error={exc}", file=sys.stderr)
            continue

        for repo in payload.get("items", []):
            full_name = repo.get("full_name") or repo.get("name")
            if not full_name or full_name in seen:
                continue
            seen.add(full_name)
            description = repo.get("description") or ""
            html_url = repo.get("html_url") or ""
            created_at = repo.get("created_at") or None
            pushed_at = repo.get("pushed_at") or created_at
            items.append(
                {
                    "title": f"{full_name}｜{description}" if description else str(full_name),
                    "summary": description,
                    "source": "GitHub",
                    "url": html_url,
                    "published_at": created_at,
                    "latest_published_at": pushed_at,
                    "topic": "github",
                    "keyword": spec["name"],
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language"),
                    "repo": full_name,
                    "sources": [{"name": "GitHub", "url": html_url}],
                }
            )
    return items


def merge_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for item in items:
        topic = str(item.get("topic") or "sports")
        key = (topic, normalize_title(str(item.get("title", ""))))
        if key not in merged:
            merged[key] = dict(item)
            continue

        existing = merged[key]
        existing_sources = existing.setdefault("sources", [])
        current_sources = item.get("sources", [])
        if isinstance(existing_sources, list) and isinstance(current_sources, list):
            known = {
                source.get("name", "").strip().lower()
                for source in existing_sources
                if isinstance(source, dict) and source.get("name")
            }
            for source in current_sources:
                if isinstance(source, dict):
                    name = source.get("name", "").strip().lower()
                    if name and name not in known:
                        existing_sources.append(source)
                        known.add(name)

        existing_keywords = existing.get("keyword")
        current_keyword = item.get("keyword")
        if existing_keywords != current_keyword:
            if isinstance(existing_keywords, list):
                if current_keyword not in existing_keywords:
                    existing_keywords.append(current_keyword)
                existing["keyword"] = existing_keywords
            else:
                existing["keyword"] = [v for v in [existing_keywords, current_keyword] if v]

        existing_latest = existing.get("latest_published_at") or existing.get("published_at")
        current_latest = item.get("latest_published_at") or item.get("published_at")
        if isinstance(current_latest, str) and (not existing_latest or current_latest > existing_latest):
            existing["latest_published_at"] = current_latest
            existing["published_at"] = current_latest
            existing["source"] = item.get("source")
            existing["url"] = item.get("url")

    return list(merged.values())


def parse_ranked_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def filter_ranked(items: list[dict[str, object]], top: int, min_score: float, reference_time: datetime) -> list[dict[str, object]]:
    def collect(max_age_hours: float) -> list[dict[str, object]]:
        kept = []
        for item in items:
            score = float(item.get("total_score", item.get("score", 0)) or 0)
            if score < min_score or item.get("topic_type") == "sports_low_value":
                continue
            latest_published_at = parse_ranked_timestamp(item.get("latest_published_at"))
            if latest_published_at is not None:
                age_hours = (reference_time - latest_published_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue
            kept.append(item)
        return kept

    filtered = collect(48)
    if len(filtered) < min(top, 8):
        filtered = collect(72)
    if not filtered:
        filtered = items[:top]
    return filtered[:top]


def main() -> int:
    args = parse_args()

    if args.reference_time:
        reference_time = datetime.fromisoformat(args.reference_time)
    else:
        reference_time = datetime.now().astimezone()

    if args.date:
        stamp = args.date
        run_date = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    else:
        stamp = today_stamp()
        run_date = reference_time.strftime("%Y-%m-%d")

    all_items: list[dict[str, object]] = []
    query_stats: list[dict[str, object]] = []

    for spec in QUERY_SPECS:
        try:
            fetched = fetch_query(spec)
            all_items.extend(fetched)
            query_stats.append({"topic": spec["topic"], "name": spec["name"], "count": len(fetched)})
        except Exception as exc:  # noqa: BLE001
            query_stats.append({"topic": spec["topic"], "name": spec["name"], "count": 0, "error": str(exc)})

    try:
        github_items = fetch_github_trending_like(stamp)
        all_items.extend(github_items)
        query_stats.append({"topic": "github", "name": "github_search_api", "count": len(github_items)})
    except Exception as exc:  # noqa: BLE001
        query_stats.append({"topic": "github", "name": "github_search_api", "count": 0, "error": str(exc)})

    merged_items = merge_items(all_items)
    ranked_items = rank_items(merged_items, args.top)

    output_dir = Path(args.output_dir)
    sources_dir = Path(args.sources_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    raw_path = sources_dir / f"{stamp}_google_news_raw.json"
    ranked_json_path = output_dir / f"{stamp}_hotspots_ranked.json"
    ranked_md_path = output_dir / f"{stamp}_hotspots_ranked.md"
    latest_json_path = output_dir / "latest_hotspots_ranked.json"
    latest_md_path = output_dir / "latest_hotspots_ranked.md"

    raw_payload = {
        "date": stamp,
        "run_date": run_date,
        "query_stats": query_stats,
        "items": merged_items,
    }

    ranked_payload = {
        "date": stamp,
        "run_date": run_date,
        "items": ranked_items,
        "topic_counts": dict(Counter(item.get("topic") for item in ranked_items)),
    }

    write_json(raw_path, raw_payload)
    write_json(ranked_json_path, ranked_payload)
    write_text(ranked_md_path, build_markdown(ranked_items, markdown_top=10))
    write_json(latest_json_path, ranked_payload)
    write_text(latest_md_path, build_markdown(ranked_items, markdown_top=10))

    print(
        json.dumps(
            {
                "ok": True,
                "raw_total": len(merged_items),
                "ranked_total": len(ranked_items),
                "query_stats": query_stats,
                "raw": str(raw_path),
                "ranked_json": str(ranked_json_path),
                "ranked_md": str(ranked_md_path),
                "latest_json": str(latest_json_path),
                "latest_md": str(latest_md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
