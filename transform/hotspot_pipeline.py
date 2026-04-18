#!/usr/bin/env python3
# Hotspot ranking pipeline for sports / ai / entertainment.

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

TOPIC_LABELS = {
    "sports": "体育热点",
    "ai": "AI科技热点",
    "entertainment": "泛娱乐热点",
    "github": "GitHub热点项目",
}
TOPIC_ORDER = ["sports", "ai", "entertainment", "github"]

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
SPORTS_PREVIEW_FORCE = ["前瞻", "赛前", "vs", "VS", "对阵", "天王山", "明晚打响", "今晚打响", "首发", "名单", "预测", "看点"]
SPORTS_RESULT_EXPLICIT = ["战报", "已晋级", "已淘汰", "出局", "赛后"]
SPORTS_RESULT_STRICT = ["晋级", "淘汰", "出局", "大胜", "轻取", "逆转", "绝平", "制胜", "破门", "领跑", "锁定", "战报"]
SPORTS_COMMENTARY_LOW = ["此前三次", "历史第", "是否", "希望", "可能性", "观点", "认为", "专注于", "完美结局", "真正重创"]

AI_HIGH_VALUE_SOURCES = ["OpenAI Blog", "Google Blog", "Anthropic", "The Verge", "TechCrunch", "量子位", "机器之心", "36氪", "新智元"]
AI_LOW_VALUE_SOURCES = ["美通社", "财富号", "车家号", "新浪财经", "搜狐", "手机新浪网"]
AI_HASH_LOW_RE = re.compile(r"^(?:#.*#){2,}.*$|^#")
AI_PRODUCT_RE = re.compile(r"(?:工具|上线|发布|推出|开发工具|智能体|agent|零代码|应用|平台|产品|助手|插件|开源|框架|代码)", re.IGNORECASE)
AI_MODEL_RE = re.compile(r"(?:模型更新|推理|参数|跑分|Claude\s*Opus|GPT|Gemini|Sora|模型能力|大模型)", re.IGNORECASE)
AI_CONTROVERSY_RE = re.compile(r"(?:泄露|曝光|版权|诉讼|监管|安全|崩了|降智|翻车)", re.IGNORECASE)
AI_LOW_VALUE_PATTERNS = ["Claude Design", "Figma", "Adobe", "设计行业", "Claude Opus 4.7", "提示词曝光", "GPT-Rosalind", "药物研发"]
AI_GOV_TRAINING_LOW = ["省属企业", "通识培训", "培训课程", "应用场景", "产业园", "示范区", "数字员工", "生态大会", "十周年", "赋能", "新范式", "联盟倡议"]
AI_BREAKING_LOW = ["早报", "一夜蒸发", "多条新闻混合", "A股", "股价", "市值"]

ENT_LOW_VALUE_PATTERNS = [
    "电影+消费", "消费市场", "市场活力", "经济图景", "集团战略", "产业发展", "多元体验", "新质赋能",
    "演唱会定档", "杏花节", "比亚迪", "充电", "续航", "km", "城市活动", "文旅活动", "消费节", "景区活动",
    "明星台企", "武术明星", "体育明星", "奥运冠军", "冠军家里", "明星大赛",
    "携手", "品牌合作", "代言", "服饰", "启动仪式", "开幕式", "大赛开幕", "活动开幕", "战略合作", "商业合作", "新时代", "产业合作", "文旅", "景区", "消费节",
]
ENT_HIGH_VALUE_PATTERNS = ["明星", "回应", "争议", "道歉", "塌房", "热搜", "票房破", "定档", "撤档", "开播", "爆了", "封神", "翻车"]
ENT_TITLE_BONUS_PATTERNS = ["票房", "定档", "上映", "电影节", "撤档", "改档", "开播", "官宣阵容", "主演", "导演", "回应", "争议", "道歉", "塌房", "翻车"]
ENT_STAR_ALLOWED_RE = re.compile(r"(?:演员|艺人|歌手|导演|主持人|爱豆|偶像|男演员|女演员|综艺|电影|电视剧)")
ENT_CONTROVERSY_RE = re.compile(r"(?:翻车|致歉|道歉|回应|终止合作|失责|开除|塌房|争议|被曝|封杀|下架)", re.IGNORECASE)

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
    latest_published_at = pick(item, "latest_published_at", "latestPublishedAt", default=published_at)
    created_at = pick(item, "created_at", "createdAt", default=published_at)
    topic = item.get("topic")
    keywords = item.get("keywords") or item.get("keywords_hit") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    stars = item.get("stars") or 0
    forks = item.get("forks") or 0
    language = item.get("language")
    repo = item.get("repo") or ""
    summary = item.get("summary") or item.get("description") or ""
    return {
        "title": title.strip(),
        "source": source.strip(),
        "url": url.strip(),
        "published_at": published_at,
        "latest_published_at": latest_published_at,
        "created_at": created_at,
        "topic": topic,
        "keywords": keywords,
        "stars": stars,
        "forks": forks,
        "language": language,
        "repo": repo,
        "summary": summary,
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
        item.get("url", ""),
        item.get("repo", ""),
        item.get("summary", ""),
        " ".join(item.get("keywords", [])),
    ])
    if "github.com" in text.lower() or item.get("source") == "GitHub" or item.get("repo"):
        return "github"
    if contains_any(text, AI_WORDS):
        return "ai"
    if contains_any(text, ENT_WORDS):
        return "entertainment"
    if contains_any(text, SPORTS_WORDS):
        return "sports"
    return "sports"


def infer_sports_type(title):
    t = title.lower()
    if contains_any(title, SPORTS_PREVIEW_FORCE):
        if not (re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, SPORTS_RESULT_EXPLICIT) or contains_any(title, ["赛后"])):
            return "sports_preview"
    if any(k.lower() in t for k in ["injury", "伤", "受伤", "复出", "leaves training", "提前离场"]):
        return "sports_injury"
    if any(k.lower() in t for k in ["refereeing", "争议", "处罚", "禁赛", "调查", "审查", "coach blast"]):
        return "sports_controversy"
    if any(k.lower() in t for k in ["transfer", "sign", "open talks", "转会", "签约", "报价", "合同", "谈判"]):
        return "sports_transfer"
    if re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, SPORTS_RESULT_STRICT):
        return "sports_result"
    if contains_any(title, ["lineups", "赛前", "名单", "抽签", "分档", "前瞻", "预测", "vs", "VS", "天王山"]):
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
    if contains_any(title, ENT_LOW_VALUE_PATTERNS):
        if "定档" in title and not contains_any(title, ["电影", "影片", "剧集", "电视剧", "综艺", "上映", "北影节"]):
            return "entertainment_low_value"
        return "entertainment_low_value"

    if ENT_CONTROVERSY_RE.search(title):
        return "entertainment_controversy"

    movie_signal = contains_any(title, ["电影", "影片", "院线", "票房", "主演", "导演", "北影节", "上映", "预告片", "撤档", "改档"])
    quoted_title = "《" in title and "》" in title
    if movie_signal and (quoted_title or contains_any(title, ["电影", "影片", "主演", "导演", "上映", "票房", "预告片", "院线", "北影节", "撤档", "改档"])):
        return "entertainment_movie"

    if contains_any(title, ["电视剧", "剧集", "开播"]):
        return "entertainment_tv"

    star_context = contains_any(title, ["演员", "艺人", "歌手", "导演", "主持人", "爱豆", "偶像", "男演员", "女演员", "综艺", "电影", "电视剧"])
    bad_star_context = contains_any(title, ["明星台企", "武术明星", "体育明星", "奥运冠军", "冠军家里", "明星大赛"])
    if star_context and not bad_star_context:
        return "entertainment_star"

    if "定档" in title:
        if not contains_any(title, ["电影", "影片", "电视剧", "剧集", "综艺", "上映", "北影节"]):
            return "entertainment_low_value"
        return "entertainment_movie"

    if contains_any(title, ["热搜", "回应", "争议", "道歉", "塌房", "翻车"]):
        return "entertainment_controversy"

    return "entertainment_hotsearch"


def infer_github_type(item):
    text = " ".join([
        item.get("title", ""),
        item.get("summary", ""),
        item.get("repo", ""),
        item.get("language", "") or "",
    ]).lower()
    repo = (item.get("repo") or "").lower()
    title = (item.get("title") or "").lower()

    if repo == "huginn/huginn":
        return "github_automation"
    if repo == "browser-use/browser-use":
        return "github_automation"
    if repo == "apache/airflow":
        return "github_automation"
    if repo == "n8n-io/n8n":
        return "github_automation"
    if repo == "puppeteer/puppeteer":
        return "github_devtool"
    if repo == "google-gemini/gemini-cli":
        return "github_devtool"
    if repo == "qwenlm/qwen-code":
        return "github_ai"
    if repo == "openhands/openhands":
        return "github_ai"
    if repo == "nousresearch/hermes-agent":
        return "github_ai"

    if any(x in repo or x in title or x in text for x in ["workflow", "automation", "bot", "scraper", "crawler", "browser-use", "browser automation", "agent that monitor", "scheduled", "trigger", "pipeline", "task runner", "orchestration", "airflow", "n8n", "huginn"]):
        return "github_automation"
    if any(x in repo or x in title or x in text for x in ["sdk", "cli", "framework", "api", "developer", "code", "compiler", "database", "storage", "minio", "filesystem", "object storage", "rustfs"]):
        return "github_devtool"
    if any(x in repo or x in title or x in text for x in ["app", "web", "ui", "dashboard", "desktop", "mobile", "frontend"]):
        return "github_app"
    if any(x in repo or x in title or x in text for x in ["llm", "agent", "openai", "chatgpt", "gemini", "claude", "rag", "diffusion", "model", "qwen", "autogpt", "langchain", "openhands", "hermes-agent"]):
        return "github_ai"
    return "github_other"


def infer_topic_type(topic, item):
    title = item.get("title", "")
    if topic == "ai":
        return infer_ai_type(title)
    if topic == "entertainment":
        return infer_ent_type(title)
    if topic == "github":
        return infer_github_type(item)
    return infer_sports_type(title)


def extract_sports_entities(title):
    m = re.search(r"(.+?)\s*(?:vs|VS|Vs)\s*(.+?)(?:[，,。：:|｜]|$)", title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(r"(.+?)\s*(?:对阵|大战)\s*(.+?)(?:[，,。：:|｜]|$)", title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def extract_ai_subject(title):
    candidates = ["OpenAI", "ChatGPT", "Claude", "Gemini", "GitHub Copilot", "英伟达", "微软", "谷歌", "Meta", "阿里", "Qwen", "Sora", "Agent", "智能体", "Meoo"]
    for c in candidates:
        if c.lower() in title.lower():
            return c
    return ""


def extract_entertainment_subject(title):
    m = re.search(r"《([^》]{2,30})》", title)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:主演|演员|歌手|导演|回应|致歉|翻车)[:：]?\s*([^，,。]{2,16})", title)
    if m:
        return m.group(1).strip()
    return ""


def sports_summary_hint(topic_type, title):
    if topic_type == "sports_preview":
        a, b = extract_sports_entities(title)
        if contains_any(title, ["vs", "VS", "对阵", "大战"]):
            if a and b:
                return f"{a}与{b}热度集中在交锋和赛前走势。"
            return "双方热度集中在交锋和赛前走势。"
        if contains_any(title, ["伤停", "出战成疑", "复出", "缺阵"]):
            return "伤停变量会影响判断，临场名单比早盘信息更关键。"
        if contains_any(title, ["前瞻", "预测"]):
            return "赛前讨论空间大，可以从对位和节奏切入。"
        if contains_any(title, ["选秀", "新秀"]):
            return "新秀话题偏长期，适合做潜力跟踪。"
        return "标题信息偏结果流，需结合热度再筛选。"
    if topic_type == "sports_result":
        if contains_any(title, ["晋级", "四强", "淘汰"]):
            return "晋级线已经明朗，后续对阵成为核心。"
        if contains_any(title, ["大胜", "轻取"]):
            return "比分已拉开，结果会影响后续排名或晋级线。"
        if contains_any(title, ["绝平", "救主", "逆转"]):
            return "比赛转折强，复盘点集中在最后阶段。"
        if contains_any(title, ["破门", "进球", "世界波"]):
            player = extract_player_from_sports(title)
            if player:
                return f"{player}表现突出，个人状态可单独成题。"
            return "个人表现突出，适合围绕核心球员做切入。"
        return "赛果已落地，重点看结果对排名和走势的影响。"
    if topic_type == "sports_injury":
        return "伤情不确定，重点看能否出战和替代方案。"
    if topic_type == "sports_transfer":
        return "转会进展值得跟进，重点看官宣概率和阵容影响。"
    if topic_type == "sports_controversy":
        return "争议正在发酵，重点看官方回应和后续处罚。"
    if topic_type == "sports_star":
        return "人物热度突出，重点看个人表现和外溢话题。"
    return "标题信息偏结果流，需结合热度再筛选。"


def extract_player_from_sports(title):
    patterns = [
        r"([\u4e00-\u9fff·]{2,8})\s*(?:破门|进球|世界波)",
        r"(?:破门|进球|世界波)[^\u4e00-\u9fff]{0,4}([\u4e00-\u9fff·]{2,8})",
        r"([A-Z][A-Za-z\-]{2,20})\s*(?:scores|goal|world class|worldie)",
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            return m.group(1).strip()
    return ""


def summary_hint(topic, topic_type, title):
    if topic == "sports":
        return sports_summary_hint(topic_type, title)
    if topic == "ai":
        subj = extract_ai_subject(title)
        low = title.lower()
        if topic_type == "ai_product":
            if any(k.lower() in low for k in ["openai", "chatgpt"]):
                return "OpenAI继续押注智能体，电脑操作是核心卖点。"
            if any(k.lower() in low for k in ["claude", "gemini"]):
                return f"{subj}产品动作明显，核心在实际使用门槛。" if subj else "产品动作明显，核心在实际使用门槛。"
            if contains_any(title, ["工具", "Agent", "智能体", "代码", "插件"]):
                return "工具属性明确，适合评估能否直接接入工作流。"
            return "产品化信号较强，偏向真实使用场景。"
        if topic_type == "ai_model":
            return "模型能力变化是核心，能否落到具体场景最关键。"
        if topic_type == "ai_controversy":
            return "争议会放大用户焦虑，重点看是否影响付费和使用信任。"
        return "公司动作更偏行业信号，适合看生态和资本变化。"
    if topic == "entertainment":
        subj = extract_entertainment_subject(title)
        if contains_any(title, ["回应", "致歉", "翻车", "终止合作"]):
            return "争议已经成型，后续看回应是否继续发酵。"
        if contains_any(title, ["定档"]):
            if subj:
                return f"《{subj}》进入宣发期，阵容和档期是主要卖点。"
            return "电影进入宣发期，阵容和档期是主要卖点。"
        if contains_any(title, ["北影节", "电影节"]):
            return "电影节话题偏行业向，适合筛明星和作品亮点。"
        if contains_any(title, ["票房", "营收", "净利"]):
            return "影视公司业绩承压，商业表现比话题更重要。"
        if contains_any(title, ["乘风", "综艺"]):
            return "综艺冲突和人设反差更容易带动热搜。"
        if contains_any(title, ["热搜"]):
            return "热搜属性强，但要判断是否能延展成完整内容。"
        return "娱乐信息偏资讯流，需要再筛人物和冲突点。"
    if topic == "github":
        if topic_type == "github_ai":
            return "AI/Agent 方向明确，适合关注模型生态和工作流接入。"
        if topic_type == "github_devtool":
            return "开发工具项目，适合评估是否能提升开发效率。"
        if topic_type == "github_automation":
            return "自动化项目，适合评估是否能替代重复操作和流程编排。"
        if topic_type == "github_app":
            return "应用型项目，适合观察产品形态和部署方式。"
        return "开源项目热度上升，适合继续观察维护频率和社区反馈。"
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


def parse_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        v = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def score_item(topic, topic_type, item):
    title = item.get("title", "")
    source = item.get("source", "")
    score = 3.0
    if topic == "sports":
        boost = {
            "sports_result": 3.0,
            "sports_preview": 2.2,
            "sports_injury": 2.5,
            "sports_transfer": 2.2,
            "sports_controversy": 2.4,
            "sports_star": 1.8,
            "sports_low_value": 0.5,
        }
    elif topic == "ai":
        boost = {"ai_product": 3.3, "ai_model": 2.6, "ai_company": 1.6, "ai_controversy": 2.5}
    elif topic == "github":
        boost = {"github_ai": 1.0, "github_devtool": 0.7, "github_automation": 0.7, "github_app": 0.6, "github_other": 0.3}
    else:
        boost = {
            "entertainment_controversy": 3.4,
            "entertainment_movie": 2.8,
            "entertainment_tv": 2.5,
            "entertainment_star": 2.2,
            "entertainment_hotsearch": 2.0,
            "entertainment_low_value": 0.2,
        }
    score += boost.get(topic_type, 1.0)

    if topic == "sports":
        if contains_any(source, SPORTS_HIGH_VALUE_SOURCES):
            score += 1.0
        if contains_any(title, SPORTS_LOW_VALUE_PATTERNS):
            score -= 1.2
        if contains_any(title, SPORTS_COMMENTARY_LOW):
            score -= 1.6
        if contains_any(title, ["前瞻", "赛前", "vs", "VS", "对阵", "天王山", "明晚", "今晚", "首发", "名单", "预测", "看点"]):
            score += 0.9
        if contains_any(title, ["冠军", "前四", "领跑", "排名"]) and not re.search(r"\d+\s*[-:比]\s*\d+", title):
            score -= 0.8
    elif topic == "ai":
        if contains_any(source, AI_HIGH_VALUE_SOURCES):
            score += 1.2
        if contains_any(source, AI_LOW_VALUE_SOURCES):
            score -= 1.0
        if AI_HASH_LOW_RE.search(title) or (title.count("#") >= 2 and len(title) < 25):
            score -= 3.0
        if contains_any(title, AI_LOW_VALUE_PATTERNS):
            score -= 1.0
        if contains_any(title, AI_GOV_TRAINING_LOW):
            score -= 1.8
        if contains_any(title, AI_BREAKING_LOW):
            score -= 1.5
        if contains_any(title, ["OpenAI", "ChatGPT", "Gemini", "Sora", "Claude", "Anthropic"]):
            score += 1.2
        if contains_any(title, ["开源", "框架", "工具", "agent", "智能体", "代码", "插件", "零代码"]):
            score += 0.9
        if AI_CONTROVERSY_RE.search(title):
            score += 0.8
    elif topic == "github":
        stars = int(item.get("stars") or 0)
        forks = int(item.get("forks") or 0)
        language = item.get("language")
        pushed_at = parse_iso_datetime(item.get("latest_published_at") or item.get("published_at"))
        created_at = parse_iso_datetime(item.get("created_at") or item.get("published_at"))
        if stars >= 10000:
            score += 3.0
        elif stars >= 3000:
            score += 2.0
        elif stars >= 1000:
            score += 1.0
        if forks >= 500:
            score += 0.8
        if language:
            score += 0.3
        if pushed_at is not None:
            age_days = (datetime.now(pushed_at.tzinfo) - pushed_at).days if pushed_at.tzinfo else (datetime.now() - pushed_at).days
            if age_days <= 7:
                score += 1.0
            elif age_days <= 30:
                score += 0.5
        if created_at is not None:
            created_age_days = (datetime.now(created_at.tzinfo) - created_at).days if created_at.tzinfo else (datetime.now() - created_at).days
            if created_age_days <= 30:
                score += 1.2
            elif created_age_days <= 90:
                score += 0.7
            if stars > 100000 and created_age_days > 365 * 2:
                score -= 1.0
            elif stars > 50000 and created_age_days > 365 * 3:
                score -= 0.8
        if topic_type == "github_ai":
            score += 0.8
        elif topic_type == "github_devtool":
            score += 0.8
        elif topic_type == "github_automation":
            score += 1.0
        elif topic_type == "github_app":
            score += 0.5
    else:
        if contains_any(title, ENT_LOW_VALUE_PATTERNS):
            score -= 2.8
        if contains_any(title, ENT_HIGH_VALUE_PATTERNS):
            score += 1.0
        if topic_type == "entertainment_low_value":
            score -= 2.2

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


def ent_event_key(title):
    if contains_any(title, ["品牌翻车", "终止合作", "创始人致歉", "男演员", "女演员"]):
        return "ent_brand_flop"
    if contains_any(title, ["回应", "道歉", "争议", "塌房", "被曝", "封杀", "下架"]):
        return "ent_controversy_generic"
    return ""


def build_ranked(items, top):
    normalized = [normalize_item(x) for x in items]
    ranked = []
    seen_by_topic = defaultdict(list)

    for item in normalized:
        if not item["title"]:
            continue
        topic = infer_topic(item)
        topic_type = infer_topic_type(topic, item)

        dup_threshold = {"sports": 0.96, "ai": 0.88, "entertainment": 0.90, "github": 0.90}.get(topic, 0.90)
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

        score = score_item(topic, topic_type, item)
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
        if topic == "github":
            out["repo"] = item.get("repo") or ""
            out["stars"] = int(item.get("stars") or 0)
            out["forks"] = int(item.get("forks") or 0)
            out["language"] = item.get("language")
            out["latest_published_at"] = item.get("latest_published_at") or item.get("published_at")
            out["created_at"] = item.get("created_at") or item.get("published_at")
            out["raw_summary"] = item.get("summary") or item.get("description") or ""
            out["summary"] = build_github_zh_summary(out)
            out["recommend_reason"] = build_github_recommend_reason(out)
        if topic == "entertainment" and topic_type == "entertainment_controversy":
            out["event_key"] = ent_event_key(item["title"])
        ranked.append(out)

    # entertainment controversy 同事件去重：只保留分数最高一条
    ent_best = {}
    final_ranked = []
    for item in ranked:
        if item["topic"] == "entertainment" and item["topic_type"] == "entertainment_controversy":
            key = item.get("event_key") or normalize_title(item["title"])
            prev = ent_best.get(key)
            if prev is None or item["score"] > prev["score"]:
                ent_best[key] = item
            continue
        final_ranked.append(item)
    final_ranked.extend(ent_best.values())

    final_ranked.sort(key=lambda x: x["score"], reverse=True)

    grouped = defaultdict(list)
    for item in final_ranked:
        grouped[item["topic"]].append(item)

    final = []
    for topic in TOPIC_ORDER:
        source_counts = Counter()
        selected = []
        for item in grouped[topic]:
            source_name = item.get("source", "") or "未知来源"
            if topic != "github" and source_counts[source_name] >= 8:
                item["score"] = round(max(0.1, item["score"] - 1.0), 2)
                continue
            source_counts[source_name] += 1
            selected.append(item)
            if len(selected) >= top:
                break
        final.extend(selected[:top])
    return final


def build_github_recommend_reason(item):
    repo = (item.get("repo") or "").lower()
    title = (item.get("title") or "").lower()
    raw = (item.get("raw_summary") or "").lower()
    topic_type = item.get("topic_type") or "github_other"
    stars = int(item.get("stars") or 0)
    pushed_at = parse_iso_datetime(item.get("latest_published_at"))
    created_at = parse_iso_datetime(item.get("created_at"))
    created_days = None
    pushed_days = None
    if created_at is not None:
        created_days = (datetime.now(created_at.tzinfo) - created_at).days if created_at.tzinfo else (datetime.now() - created_at).days
    if pushed_at is not None:
        pushed_days = (datetime.now(pushed_at.tzinfo) - pushed_at).days if pushed_at.tzinfo else (datetime.now() - pushed_at).days

    def recent_phrase():
        if pushed_days is not None and pushed_days <= 7:
            return "近期仍活跃"
        if created_days is not None and created_days <= 30:
            return "近期新项目"
        if created_days is not None and created_days <= 90:
            return "近期增长较快"
        return ""

    if any(k in repo for k in ["career-ops"]):
        return "把求职流程做成自动化系统，适合拆成效率工具选题。"
    if any(k in repo for k in ["everything-claude-code"]):
        return "围绕 Claude Code 做工具集合，适合追踪开发者工作流。"
    if any(k in repo for k in ["hermes-agent"]):
        return "Agent长期记忆方向明确，可观察个人助手形态。"
    if any(k in repo for k in ["openhands"]):
        return "AI写代码和执行任务结合，适合看自动开发边界。"
    if any(k in repo for k in ["chattts"]):
        return "语音生成场景明确，适合关注内容生产应用。"
    if any(k in repo for k in ["ragflow"]):
        return "RAG和知识库结合紧密，适合企业文档问答场景。"
    if any(k in repo for k in ["llamafactory"]):
        return "微调门槛降低，适合追踪开源模型训练工具。"
    if any(k in repo for k in ["huginn", "browser-use", "airflow", "n8n"]):
        return "自动化流程价值明确，适合接入采集和发布链路。"

    parts = []
    if stars > 100000:
        parts.append("社区规模大")
    if topic_type == "github_automation":
        parts.append("自动化流程价值明确")
    elif topic_type == "github_devtool":
        parts.append("开发效率导向明显")
    elif topic_type == "github_ai":
        parts.append("AI/Agent 方向明确")
    elif topic_type == "github_app":
        parts.append("应用落地路径清晰")
    if recent_phrase():
        parts.append(recent_phrase())
    if not parts:
        parts.append("适合继续观察")
    reason = "，".join(parts) + "。"
    if len(reason) > 50:
        reason = reason[:50].rstrip("，。") + "。"
    return reason


def build_github_zh_summary(item):
    repo = (item.get("repo") or "").lower()
    title = (item.get("title") or "").lower()
    raw = (item.get("raw_summary") or "").lower()
    topic_type = item.get("topic_type") or "github_other"
    text = " ".join([repo, title, raw, topic_type.lower()])

    if any(k in text for k in ["langchain"]):
        return "Agent 和 LLM 应用开发框架，适合搭建复杂 AI 工作流。"
    if any(k in text for k in ["hermes-agent"]):
        return "面向个人和团队的 AI Agent 项目，强调长期记忆和协作能力。"
    if any(k in text for k in ["openhands"]):
        return "AI 编程代理，主打自动完成开发任务和代码协作。"
    if any(k in text for k in ["chattts"]):
        return "文本转语音模型，适合语音生成和对话音频场景。"
    if any(k in text for k in ["llms-from-scratch"]):
        return "从零实现大模型的教程项目，适合学习 LLM 底层原理。"
    if any(k in text for k in ["ragflow"]):
        return "RAG 检索增强生成引擎，适合知识库问答和企业文档场景。"
    if any(k in text for k in ["llamafactory"]):
        return "大模型微调工具，适合训练和适配开源模型。"
    if any(k in text for k in ["huginn"]):
        return "自动化代理工具，可监控网页事件并触发任务流程。"
    if any(k in text for k in ["browser-use"]):
        return "浏览器自动化工具，适合网页操作、采集和自动任务。"
    if any(k in text for k in ["airflow"]):
        return "任务编排平台，适合数据流、定时任务和自动化管道。"
    if any(k in text for k in ["n8n"]):
        return "低代码自动化平台，适合连接 API、表格和多平台发布流程。"
    if any(k in text for k in ["puppeteer"]):
        return "浏览器控制工具，适合网页截图、爬取和自动化测试。"
    if any(k in text for k in ["gemini-cli"]):
        return "Gemini 命令行工具，适合在终端中调用 AI 能力。"
    if any(k in text for k in ["qwen-code"]):
        return "通义千问代码 Agent，适合代码生成、重构和开发辅助。"
    if topic_type == "github_ai":
        return "AI/Agent 相关项目，适合观察模型生态和应用落地。"
    if topic_type == "github_devtool":
        return "开发工具项目，适合评估是否能提升开发效率。"
    if topic_type == "github_automation":
        return "自动化项目，适合评估是否能替代重复操作和流程编排。"
    if topic_type == "github_app":
        return "应用型项目，适合观察产品形态和部署方式。"
    return "开源项目热度上升，适合继续观察维护频率和社区反馈。"


def display_title(title, limit=60):
    text = str(title or "")
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def github_display_usage(item):
    summary = (item.get("summary") or item.get("description") or "").strip()
    if not summary:
        title = item.get("title") or ""
        if "｜" in title:
            summary = title.split("｜", 1)[1].strip()
        else:
            summary = title.strip()
    if len(summary) > 90:
        return summary[:90] + "..."
    return summary


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
            if topic == "github":
                repo = item.get("repo") or item.get("title", "")
                lines.append(f"### {i}. {repo}")
                lines.append(f"- 类型：{item.get('topic_type', '')}")
                lines.append(f"- 语言：{item.get('language') or '未知'}")
                lines.append(f"- Stars：{item.get('stars', 0)}")
                lines.append(f"- Forks：{item.get('forks', 0)}")
                lines.append(f"- 用途：{github_display_usage(item)}")
                lines.append(f"- 推荐理由：{item.get('recommend_reason', '')}")
                lines.append(f"- 链接：{item.get('url', '')}")
                lines.append("")
                continue

            title = display_title(item['title'])
            lines.append(f"### {i}. {title}")
            lines.append(f"- topic：{item['topic']}")
            lines.append(f"- topic_type：{item['topic_type']}")
            lines.append(f"- score：{item['score']}")
            lines.append(f"- 概述：{item['summary_hint']}")
            if item.get("event_key"):
                lines.append(f"- event_key：{item['event_key']}")
            lines.append("- 来源：")
            for src in item.get("sources", [])[:3]:
                src_title = display_title(src.get('title', ''))
                lines.append(f"  - {src.get('source','')}｜{src_title}")
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
