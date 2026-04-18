#!/usr/bin/env python3
# Hotspot ranking pipeline for sports / ai / entertainment.

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

TOPIC_LABELS = {
    "sports": "体育热点",
    "ai": "AI科技热点",
    "entertainment": "泛娱乐热点",
}
TOPIC_ORDER = ["sports", "ai", "entertainment"]

SPORTS_WORDS = [
    "英超", "NBA", "欧冠", "中超", "意甲", "德甲", "法甲", "亚冠", "梅西", "C罗",
    "球队", "比赛", "晋级", "进球", "比分", "主场", "客场", "女篮", "男篮",
    "WTT", "斯诺克", "WCBA", "勇士", "太阳", "湖人", "曼联", "曼城", "国米",
    "Inter", "Milan", "Warriors", "Rockets", "Mbappe", "Liverpool", "Serie A",
]
AI_WORDS = [
    "OpenAI", "ChatGPT", "Gemini", "Sora", "Claude", "英伟达", "苹果AI", "模型",
    "人工智能", "大模型", "推理", "智能体", "NVIDIA", "Google AI", "Agent",
]
ENT_WORDS = [
    "微博热搜", "电影", "电视剧", "综艺", "明星", "演员", "导演", "票房",
    "热搜", "定档", "上映", "回应争议", "娱乐",
]

SPORTS_HIGH_VALUE_SOURCES = ["懂球帝", "直播吧", "体坛周报", "虎扑", "ESPN", "Sky Sports", "The Athletic", "Reuters", "AP"]
SPORTS_LOW_VALUE_PATTERNS = ["集锦", "录像", "回放", "直播安排", "赛程表", "节目表"]

AI_HIGH_VALUE_SOURCES = ["OpenAI Blog", "Google Blog", "Anthropic", "The Verge", "TechCrunch", "量子位", "机器之心", "36氪", "新智元"]
AI_LOW_VALUE_SOURCES = ["美通社", "财富号", "车家号", "新浪财经", "搜狐", "手机新浪网"]
AI_HASH_LOW_RE = re.compile(r"^(?:#.*#){2,}.*$|^#")
AI_PRODUCT_RE = re.compile(r"(?:工具|上线|发布|推出|开发工具|智能体|agent|零代码|应用|平台|产品|助手|插件)", re.IGNORECASE)
AI_MODEL_RE = re.compile(r"(?:模型更新|推理|参数|跑分|Claude\s*Opus|GPT|Gemini|Sora|模型能力|大模型)", re.IGNORECASE)
AI_CONTROVERSY_RE = re.compile(r"(?:泄露|曝光|版权|诉讼|监管|安全|崩了|降智|翻车)", re.IGNORECASE)
AI_LOW_VALUE_PATTERNS = ["Claude Design", "Figma", "Adobe", "设计行业", "Claude Opus 4.7", "提示词曝光", "GPT-Rosalind", "药物研发"]

ENT_LOW_VALUE_PATTERNS = [
    "电影+消费", "消费市场", "市场活力", "经济图景", "集团战略", "产业发展", "多元体验", "新质赋能",
    "演唱会定档", "杏花节", "比亚迪", "充电", "续航", "km", "城市活动", "文旅活动", "消费节", "景区活动",
]
ENT_HIGH_VALUE_PATTERNS = ["明星", "回应", "争议", "道歉", "塌房", "热搜", "票房破", "定档", "撤档", "开播", "爆了", "封神", "翻车"]
ENT_TITLE_BONUS_PATTERNS = ["票房", "定档", "上映", "电影节", "撤档", "改档", "开播", "官宣阵容", "主演", "导演", "回应", "争议", "道歉", "塌房", "翻车"]

TITLE_PARTY_PATTERNS = ["终于", "炸了", "塌了", "全网热议", "太敢说", "万万没想到", "惊呆", "杀疯了"]

SOURCE_SUFFIX_RE = re.compile(r"(?:\s*[-—|｜]\s*[^-—|｜]{2,24})+$")
SPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-json", required=False)
    ap.add_argument("--output-markdown", required=False)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--reference-time", required=False)
    return ap.parse_args()


def load_json(path):
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "articles", "news", "data", "entries"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def pick(item, *names, default=""):
    for n in names:
        v = item.get(n)
        if v:
            return str(v)
    return default


def normalize_item(item):
    title = pick(item, "title", "headline", "name")
    source = pick(item, "source", "publisher", "site", "source_name")
    url = pick(item, "url", "link")
    published_at = pick(item, "published_at", "published", "pubDate", "date", "time")
    topic = item.get("topic")
    keywords = item.get("keywords") or item.get("keywords_hit") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    return {
        "title": title.strip(),
        "source": source.strip(),
        "url": url.strip(),
        "published_at": published_at,
        "topic": topic,
        "keywords": keywords,
        "raw": item,
    }


def contains_any(text, words):
    lower = text.lower()
    return any(w.lower() in lower for w in words)


def infer_topic(item):
    topic = item.get("topic")
    if topic in TOPIC_LABELS:
        return topic
    text = " ".join([
        item.get("title", ""),
        item.get("source", ""),
        " ".join(item.get("keywords", [])),
    ])
    if contains_any(text, AI_WORDS):
        return "ai"
    if contains_any(text, ENT_WORDS):
        return "entertainment"
    if contains_any(text, SPORTS_WORDS):
        return "sports"
    return "sports"


def infer_sports_type(title):
    t = title.lower()
    if any(k.lower() in t for k in ["injury", "伤", "受伤", "复出", "leaves training", "提前离场"]):
        return "sports_injury"
    if any(k.lower() in t for k in ["refereeing", "争议", "处罚", "禁赛", "调查", "审查", "coach blast"]):
        return "sports_controversy"
    if any(k.lower() in t for k in ["transfer", "sign", "open talks", "转会", "签约", "报价", "合同", "谈判"]):
        return "sports_transfer"
    if re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, ["晋级", "出局", "逆转", "爆冷", "大胜", "绝杀", "夺冠", "领跑", "淘汰", "冠军", "eliminate", "eliminates", "clinch", "clinches", "comeback win"]):
        return "sports_result"
    if contains_any(title, ["lineups", "赛前", "名单", "抽签", "分档", "前瞻", "预测", "vs", "VS"]):
        return "sports_preview"
    if contains_any(title, ["梅西", "C罗", "Mbappe", "Ohtani", "球星"]):
        return "sports_star"
    return "sports_low_value"


def infer_ai_type(title):
    if AI_CONTROVERSY_RE.search(title):
        return "ai_controversy"
    if AI_PRODUCT_RE.search(title):
        return "ai_product"
    if AI_MODEL_RE.search(title):
        return "ai_model"
    return "ai_company"


def infer_ent_type(title):
    # 低质/误伤先拦截
    if contains_any(title, ENT_LOW_VALUE_PATTERNS):
        # 如果是“定档”但不是电影/剧集/综艺/电影节，默认低价值
        if "定档" in title and not contains_any(title, ["电影", "影片", "剧集", "电视剧", "综艺", "上映", "电影节"]):
            return "entertainment_low_value"
        # 演唱会/城市活动/文旅/车企发布等都直接低价值
        return "entertainment_low_value"

    # 真正的电影类：不能只靠“定档”判断，必须有更明确电影信号
    movie_signal = contains_any(title, ["电影", "影片", "院线", "票房", "主演", "导演", "北影节", "上映", "预告片", "撤档", "改档"])
    quoted_title = "《" in title and "》" in title
    if movie_signal and (quoted_title or contains_any(title, ["电影", "影片", "主演", "导演", "上映", "票房", "预告片", "院线", "北影节", "撤档", "改档"])):
        return "entertainment_movie"

    if contains_any(title, ["电视剧", "剧集", "开播"]):
        return "entertainment_tv"
    if contains_any(title, ["明星", "演员", "艺人"]):
        return "entertainment_star"
    if contains_any(title, ["回应", "争议", "道歉", "塌房", "翻车", "热搜"]):
        return "entertainment_controversy"
    if "定档" in title:
        # 不是明确电影/剧集/综艺的一律低价值
        if not contains_any(title, ["电影", "影片", "电视剧", "剧集", "综艺", "上映", "北影节"]):
            return "entertainment_low_value"
        return "entertainment_movie"
    return "entertainment_hotsearch"


def infer_topic_type(topic, title):
    if topic == "ai":
        return infer_ai_type(title)
    if topic == "entertainment":
        return infer_ent_type(title)
    return infer_sports_type(title)


def summary_hint(topic, topic_type, title):
    if topic == "sports":
        if topic_type == "sports_preview":
            return "赛前看点更强，重点看首发、对位和临场变化。"
        if topic_type == "sports_result":
            return "赛果和关键回合值得继续复盘。"
        if topic_type == "sports_injury":
            return "伤情不确定，重点看能否出战和替代方案。"
        if topic_type == "sports_transfer":
            return "转会进展值得跟进，重点看官宣概率和阵容影响。"
        if topic_type == "sports_controversy":
            return "争议正在发酵，重点看官方回应和后续处罚。"
        if topic_type == "sports_star":
            return "人物热度突出，重点看个人表现和外溢话题。"
        return "体育资讯热度一般，适合作为补充观察。"
    if topic == "ai":
        if topic_type == "ai_product":
            return "工具或产品发布更看重实际使用价值和上手体验。"
        if topic_type == "ai_model":
            return "模型更新会直接影响能力表现和用户体验。"
        if topic_type == "ai_controversy":
            return "争议或监管信号值得继续跟进。"
        return "公司动态可能影响行业预期和产品节奏。"
    if topic == "entertainment":
        if topic_type == "entertainment_movie":
            return "电影相关信息适合看票房、定档和市场反馈。"
        if topic_type == "entertainment_tv":
            return "剧集热度适合观察口碑和播放表现。"
        if topic_type == "entertainment_star":
            return "人物动态适合观察舆论扩散和粉丝反馈。"
        if topic_type == "entertainment_controversy":
            return "争议和舆论走向值得继续跟进。"
        if topic_type == "entertainment_low_value":
            return "更适合作为补充信息，不宜放高优先级。"
        return "热搜事件适合观察传播速度和讨论点。"
    return "热点可继续观察。"


def clean_title_for_match(title):
    s = title.lower()
    s = SOURCE_SUFFIX_RE.sub("", s)
    s = SPACE_RE.sub("", s)
    s = re.sub(r"[\-—_|｜:：,，。.!！？?（）()【】\[\]<>《》'\"“”]+", "", s)
    s = s.replace("手机新浪网", "").replace("新浪网", "").replace("央视体育", "")
    return s


def title_similarity(a, b):
    a_norm = clean_title_for_match(a)
    b_norm = clean_title_for_match(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def title_quality_score(topic, title):
    score = 4.0
    compact = re.sub(r"\s+", "", title)
    length = len(compact)
    if length < 8:
        score -= 2.0
    elif length > 55:
        score -= 0.7

    if all(ch.isdigit() or ch in "#-_" for ch in compact):
        score -= 2.0
    if compact.count("#") >= 2 and length < 25:
        score -= 2.5
    if title.startswith("#"):
        score -= 1.5
    if contains_any(title, TITLE_PARTY_PATTERNS):
        score -= 1.2
    if contains_any(title, ["今日", "一夜消息", "恭喜", "正式确认", "曝", "终于"]):
        score -= 0.4
    if topic == "sports" and contains_any(title, SPORTS_LOW_VALUE_PATTERNS):
        score -= 1.0
    if topic == "ai" and contains_any(title, ["跑分", "提示词", "曝光"]):
        score -= 0.8
    if topic == "entertainment" and contains_any(title, ENT_LOW_VALUE_PATTERNS):
        score -= 1.5
    return round(max(score, 0.0), 2)


def score_item(topic, topic_type, title, source):
    score = 3.0
    if topic == "sports":
        boost = {
            "sports_result": 3.0,
            "sports_preview": 2.0,
            "sports_injury": 2.5,
            "sports_transfer": 2.2,
            "sports_controversy": 2.4,
            "sports_star": 1.8,
            "sports_low_value": 0.5,
        }
    elif topic == "ai":
        boost = {"ai_product": 3.3, "ai_model": 2.6, "ai_company": 1.6, "ai_controversy": 2.5}
    else:
        boost = {
            "entertainment_controversy": 3.0,
            "entertainment_movie": 2.8,
            "entertainment_tv": 2.5,
            "entertainment_star": 2.4,
            "entertainment_hotsearch": 2.0,
            "entertainment_low_value": 0.3,
        }
    score += boost.get(topic_type, 1.0)

    if topic == "sports":
        if contains_any(source, SPORTS_HIGH_VALUE_SOURCES):
            score += 1.0
        if contains_any(title, SPORTS_LOW_VALUE_PATTERNS):
            score -= 1.2
    elif topic == "ai":
        if contains_any(source, AI_HIGH_VALUE_SOURCES):
            score += 1.2
        if contains_any(source, AI_LOW_VALUE_SOURCES):
            score -= 1.0
        if AI_HASH_LOW_RE.search(title) or (title.count("#") >= 2 and len(title) < 25):
            score -= 3.0
        if contains_any(title, AI_LOW_VALUE_PATTERNS):
            score -= 1.0
    else:
        if contains_any(title, ENT_LOW_VALUE_PATTERNS):
            score -= 2.5
        if contains_any(title, ENT_HIGH_VALUE_PATTERNS):
            score += 1.2
        if "定档" in title and topic_type == "entertainment_low_value":
            score -= 2.0

    trusted = ["央视", "新华", "人民网", "ESPN", "BBC", "Reuters", "AP"]
    if contains_any(source, trusted):
        score += 0.5

    if len(title) > 42:
        score -= 0.2

    score += 0.18 * title_quality_score(topic, title)
    return round(max(score, 0.1), 2)


def domain(url):
    if not url:
        return ""
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def normalize_title(title):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", title.lower())
    for w in ["新浪网", "手机新浪网", "搜狐网", "央视体育"]:
        s = s.replace(w.lower(), "")
    return s[:80]


def build_ranked(items, top):
    normalized = [normalize_item(x) for x in items]
    ranked = []
    seen_by_topic = defaultdict(list)

    for item in normalized:
        if not item["title"]:
            continue
        topic = infer_topic(item)
        topic_type = infer_topic_type(topic, item["title"])

        dup_threshold = {"sports": 0.96, "ai": 0.88, "entertainment": 0.90}.get(topic, 0.90)
        is_dup = False
        for prev in seen_by_topic[topic]:
            if normalize_title(prev["title"]) == normalize_title(item["title"]):
                is_dup = True
                break
            if title_similarity(prev["title"], item["title"]) >= dup_threshold:
                is_dup = True
                break
        if is_dup:
            continue
        seen_by_topic[topic].append(item)

        score = score_item(topic, topic_type, item["title"], item["source"])
        out = {
            "title": item["title"],
            "source": item["source"],
            "url": item["url"],
            "topic": topic,
            "topic_type": topic_type,
            "score": score,
            "summary_hint": summary_hint(topic, topic_type, item["title"]),
            "sources": [{
                "source": item["source"],
                "title": item["title"],
                "url": item["url"],
                "domain": domain(item["url"]),
            }],
        }
        ranked.append(out)

    ranked.sort(key=lambda x: x["score"], reverse=True)

    grouped = defaultdict(list)
    for item in ranked:
        grouped[item["topic"]].append(item)

    final = []
    for topic in TOPIC_ORDER:
        source_counts = Counter()
        selected = []
        for item in grouped[topic]:
            source_name = item.get("source", "") or "未知来源"
            if source_counts[source_name] >= 8:
                item["score"] = round(max(0.1, item["score"] - 1.0), 2)
                continue
            source_counts[source_name] += 1
            selected.append(item)
            if len(selected) >= top:
                break
        final.extend(selected[:top])
    return final


def render_markdown(items, markdown_top=10):
    lines = ["# 今日热点候选", ""]
    grouped = defaultdict(list)
    for item in items:
        grouped[item.get("topic", "sports")].append(item)

    for topic in TOPIC_ORDER:
        arr = grouped.get(topic, [])[:markdown_top]
        lines.append(f"## {TOPIC_LABELS[topic]}")
        lines.append("")
        if not arr:
            lines.append("_暂无候选_")
            lines.append("")
            continue
        for i, item in enumerate(arr, 1):
            lines.append(f"### {i}. {item['title']}")
            lines.append(f"- topic：{item['topic']}")
            lines.append(f"- topic_type：{item['topic_type']}")
            lines.append(f"- score：{item['score']}")
            lines.append(f"- 摘要：{item['summary_hint']}")
            lines.append("- 来源：")
            for src in item.get("sources", [])[:3]:
                lines.append(f"  - {src.get('source','')}｜{src.get('title','')}")
                if src.get("domain"):
                    lines.append(f"    链接：{src.get('domain')}")
            lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    raw_items = load_json(args.input)
    ranked = build_ranked(raw_items, args.top)
    counts = Counter(x["topic"] for x in ranked)
    payload = {"items": ranked, "topic_counts": dict(counts)}

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_markdown:
        Path(args.output_markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_markdown).write_text(render_markdown(ranked, markdown_top=10), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "total": len(ranked),
        "topic_counts": dict(counts),
        "output_json": args.output_json,
        "output_markdown": args.output_markdown,
    }, ensure_ascii=False, indent=2))


def rank_items(items, top=20, reference_time=None):
    if not isinstance(top, int):
        top = 20
    return build_ranked(items, top)


def build_markdown(items, markdown_top=10):
    return render_markdown(items, markdown_top=markdown_top)


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
