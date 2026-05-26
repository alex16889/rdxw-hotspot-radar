#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily multi-topic hotspot runner.

- Fetches Google News RSS for sports / esports / ai / entertainment / x / youtube
- Fetches GitHub Search API for GitHub project candidates
- Merges duplicate headlines across queries
- Invokes transform.hotspot_pipeline for ranking + Markdown rendering
- Writes a dashboard-facing ranked payload under output/
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sys
from collections import Counter
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from functools import lru_cache
from html import escape, unescape
from pathlib import Path
from urllib.parse import quote, quote_plus, urlparse
from xml.etree import ElementTree as ET

import requests

from transform.hotspot_pipeline import build_markdown, rank_items, write_json, write_text

ROOT = Path(__file__).resolve().parent
SITE_BASE_URL = os.environ.get("HOTSPOT_SITE_URL", "https://rdxw.cc").rstrip("/")
DETAIL_RETENTION_DAYS_DEFAULT = 30
ANALYTICS_SNIPPET = """  <script charset="UTF-8" id="LA_COLLECT" src="//sdk.51.la/js-sdk-pro.min.js"></script>
  <script>LA.init({id:"L6V4CYa27UR83MWj",ck:"L6V4CYa27UR83MWj"})</script>"""
SPONSOR_DESKTOP_TEXT = "世界杯直播观看，体育电竞福利，注册即送100"
SPONSOR_MOBILE_TEXT = "世界杯直播观看"
INDEXNOW_KEY_FILE = "indexnow-key.txt"
INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")
ALL_TOPICS = ("sports", "esports", "ai", "entertainment", "platform", "github")
PLATFORM_TOPICS = {"x", "youtube"}
DAILY_BRIEF_SECTIONS = (
    {"key": "sports", "label": "体育", "topic": "sports"},
    {"key": "esports", "label": "电竞", "topic": "esports"},
    {"key": "github", "label": "GitHub", "topic": "github"},
    {"key": "ai", "label": "AI", "topic": "ai"},
    {"key": "x", "label": "X", "topic": "platform", "source_topic": "x"},
    {"key": "youtube", "label": "YouTube", "topic": "platform", "source_topic": "youtube"},
)
TOPIC_SLUGS = {
    "sports": "sports",
    "esports": "esports",
    "ai": "ai",
    "entertainment": "entertainment",
    "platform": "platform",
    "github": "github",
}
PUBLIC_TOPIC_LABELS = {
    "sports": "体育热点",
    "esports": "电竞热点",
    "ai": "AI科技热点",
    "entertainment": "泛娱乐热点",
    "platform": "平台热议",
    "github": "GitHub热点项目",
}
WINDOW_SLUGS = {"1d": "24h", "3d": "3d", "7d": "7d"}
TRANSLATE_API_URL = "https://translate.googleapis.com/translate_a/single"
ENGLISH_RE = re.compile(r"[A-Za-z]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
URL_RE = re.compile(r"https?://\S+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
ESPORTS_SOURCE_SUFFIX_RE = re.compile(
    r"\s*[-—]\s*[^-—|｜]{1,24}\s*[-—]\s*(?:Score[-—]?电竞玩家赛事社区|scoregg\.com)\s*$",
    re.IGNORECASE,
)
GOOGLE_NEWS_NETWORK_RESOLVE_USED = 0
DOMESTIC_SITE_FILTER = (
    "(site:sports.sina.com.cn OR site:sports.qq.com OR site:sports.163.com OR "
    "site:sports.cctv.com OR site:sports.people.com.cn OR site:news.sports.cn OR "
    "site:sports.sohu.com)"
)
PLATFORM_KEYWORDS = [
    "NBA", "欧冠", "英超", "中超", "WTT", "斯诺克", "CBA", "WCBA",
    "OpenAI", "ChatGPT", "Claude", "Gemini", "Sora", "人工智能", "大模型",
    "LPL", "KPL", "英雄联盟", "无畏契约", "电竞",
    "电影", "电视剧", "综艺", "明星", "票房", "导演",
]
PLATFORM_KEEP_SIGNAL_RE = re.compile(
    r"(openai|chatgpt|claude|gemini|sora|人工智能|大模型|\bai\b|\bagent\b|"
    r"世界杯|nba|cba|wcba|中超|国足|欧冠|英超|wtt|斯诺克|lpl|kpl|msi|cs2|"
    r"valorant|无畏契约|英雄联盟|王者荣耀|电竞|github|开源|发布|官宣|回应|争议|"
    r"事故|处罚|封禁|下架|诉讼|监管)",
    re.IGNORECASE,
)
PLATFORM_VIDEO_NOISE_RE = re.compile(
    r"(telugu|hindi|serial|episode|full\s*episode|watch\s*full|promo|trailer|teaser|"
    r"official\s*promo|official\s*teaser|sun\s*tv|gemini\s*tv|zee\s*tv|star\s*plus|"
    r"anime|donghua|drama|c-?drama|season\s*\d+|s\d+e\d+|ep(?:isode)?\.?\s*\d+|"
    r"泰卢固|印地语|连续剧|电视剧|剧集|短剧|全集|第\s*\d+\s*集|"
    r"预告片|先导片|片段|动漫|动画|古装剧|宫斗|历史传奇剧)",
    re.IGNORECASE,
)
TRANSLATION_FALLBACKS = {
    "live now": "正在直播",
    "live!": "直播！",
    "live:": "直播：",
    "official trailer": "官方预告",
    "official teaser": "官方预告",
    "official clip": "官方片段",
    "official video": "官方视频",
    "official": "官方",
    "live stream": "直播",
    "livestream": "直播",
    "live": "直播",
    "highlights": "精彩片段",
    "highlight": "精彩片段",
    "shorts": "短视频",
    "short": "短视频",
    "interview": "采访",
    "podcast": "播客",
    "breakdown": "拆解",
    "explained": "解读",
    "analysis": "分析",
    "reaction": "回应",
    "reacts": "回应",
    "thread": "长帖",
    "post": "帖子",
    "update": "更新",
    "launch": "发布",
    "launches": "发布",
    "released": "发布",
    "release": "发布",
    "announced": "宣布",
    "announcement": "公告",
    "trailer": "预告",
    "teaser": "预告",
    "in cinemas": "院线上映",
    "session 1": "第一节",
    "session 2": "第二节",
    "day 1": "第1天",
    "day 2": "第2天",
    "day 3": "第3天",
    "feeder": "支线赛",
    "review": "评测",
    "preview": "前瞻",
    "recap": "回顾",
    "wins": "击败",
    "beat": "击败",
    "beats": "击败",
    "defeats": "击败",
    "vs": "对阵",
}
TRANSLATION_POST_FIXES = {
    "居住！": "直播！",
    "居住": "直播",
    "现场直播": "直播",
    "预告片": "预告",
    "院线 1 may": "院线 5月1日上映",
}

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
        "query": "(NBA OR 欧冠 OR 英超 OR 意甲 OR 德甲 OR 中超 OR 亚冠 OR WTT OR 斯诺克 OR WCBA OR 女篮) (site:dongqiudi.com OR site:zhibo8.cc OR site:hupu.com OR site:titan24.com OR site:ppsports.com) when:1d",
        "required_keywords": ["NBA", "欧冠", "英超", "意甲", "德甲", "中超", "亚冠", "WTT", "斯诺克", "WCBA", "女篮"],
    },
    {
        "topic": "sports",
        "name": "sports_media_cn",
        "query": "(NBA OR 欧冠 OR 英超 OR 意甲 OR 德甲 OR 中超 OR 亚冠 OR WTT OR 斯诺克 OR WCBA OR 女篮) (site:ppsports.com OR site:zhibo8.cc OR site:hupu.com OR site:titan24.com OR site:dongqiudi.com) when:1d",
        "required_keywords": ["NBA", "欧冠", "英超", "意甲", "德甲", "中超", "亚冠", "WTT", "斯诺克", "WCBA", "女篮"],
    },
    # esports
    {
        "topic": "esports",
        "name": "domestic_esports_cn",
        "query": "(电竞 OR 电子竞技 OR 英雄联盟 OR 王者荣耀 OR LPL OR KPL OR DOTA2 OR CS2 OR 无畏契约) (site:5eplay.com OR site:scoregg.com OR site:wanplus.cn OR site:uuu9.com OR site:play.163.com OR site:news.17173.com) when:1d",
        "required_keywords": ["电竞", "电子竞技", "英雄联盟", "王者荣耀", "LPL", "KPL", "DOTA2", "CS2", "无畏契约", "战队"],
    },
    {
        "topic": "esports",
        "name": "global_esports_cn",
        "query": "(电竞 OR 英雄联盟 OR 王者荣耀 OR LPL OR KPL OR DOTA2 OR CS2 OR 无畏契约 OR MSI OR 世界赛) (Reuters OR AP OR ESPN OR The Athletic OR 5EPlay OR 兔玩 OR 玩加电竞) when:1d",
        "required_keywords": ["电竞", "英雄联盟", "王者荣耀", "LPL", "KPL", "DOTA2", "CS2", "无畏契约", "MSI", "世界赛"],
    },
    {
        "topic": "esports",
        "name": "esports_hot_cn",
        "query": "(夺冠 OR 晋级 OR 出局 OR 复盘 OR 转会 OR 续约 OR 争议 OR 处罚) (电竞 OR 英雄联盟 OR 王者荣耀 OR LPL OR KPL OR DOTA2 OR CS2 OR 无畏契约) when:1d",
        "required_keywords": ["夺冠", "晋级", "出局", "复盘", "转会", "续约", "争议", "处罚", "英雄联盟", "王者荣耀"],
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
    # x
    {
        "topic": "x",
        "name": "x_hot_cn",
        "query": f"((site:x.com OR site:twitter.com) ({' OR '.join(PLATFORM_KEYWORDS)})) when:1d",
        "required_keywords": PLATFORM_KEYWORDS + ["thread", "post", "tweet", "官方", "直播", "预告", "采访"],
        "default_source": "X",
    },
    {
        "topic": "x",
        "name": "x_breaking_cn",
        "query": f"((site:x.com OR site:twitter.com) (({' OR '.join(PLATFORM_KEYWORDS)}) (breaking OR official OR announced OR trailer OR highlights OR interview OR podcast OR 发布 OR 官宣 OR 回应 OR 采访))) when:1d",
        "required_keywords": PLATFORM_KEYWORDS,
        "default_source": "X",
    },
    # youtube
    {
        "topic": "youtube",
        "name": "youtube_hot_cn",
        "query": f"((site:youtube.com) ({' OR '.join(PLATFORM_KEYWORDS)})) when:1d",
        "required_keywords": PLATFORM_KEYWORDS + ["live", "shorts", "trailer", "interview", "podcast", "视频", "直播", "预告"],
        "default_source": "YouTube",
    },
    {
        "topic": "youtube",
        "name": "youtube_video_cn",
        "query": f"((site:youtube.com) (({' OR '.join(PLATFORM_KEYWORDS)}) (live OR shorts OR trailer OR interview OR podcast OR highlights OR 视频 OR 直播 OR 预告 OR 采访))) when:1d",
        "required_keywords": PLATFORM_KEYWORDS,
        "default_source": "YouTube",
    },
]

GOOGLE_NEWS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135 Safari/537.36",
}
WINDOW_SPECS = [
    {"key": "1d", "label": "24小时", "days": 1},
    {"key": "3d", "label": "3天", "days": 3},
    {"key": "7d", "label": "7天", "days": 7},
]
SOURCE_RADAR_API = os.environ.get("HOTSPOT_SOURCE_RADAR_API", "https://newsnow.busiyi.world").rstrip("/")
SOURCE_RADAR_CONFIG_PATH = ROOT / "config" / "source_radar_sources.json"
SOURCE_RADAR_CACHE_DIR = ROOT / os.environ.get("HOTSPOT_SOURCE_RADAR_CACHE_DIR", "sources/source_radar_cache")
LLM_EDITORIAL_VERSION = "rdxw_llm_editorial_v1"
LLM_EDITORIAL_CACHE_PATH = ROOT / os.environ.get("HOTSPOT_LLM_EDITORIAL_CACHE", "sources/llm_editorial_cache.json")
OPENAI_RESPONSES_URL = os.environ.get("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
DEFAULT_LLM_MODEL = os.environ.get("HOTSPOT_LLM_MODEL", "gpt-5.5")
KNOWN_LLM_NON_CORE_ERROR_CODES = {"unsupported_country_region_territory"}
SEO_TOPIC_CLUSTERS = [
    {
        "slug": "zhongchao-hot",
        "label": "中超热点",
        "description": "聚合一周内中超、国足、足协杯和国内足球强赛果，适合做赛后复盘和下一轮走势。",
        "topics": ["sports"],
        "keywords": ["中超", "国足", "足协杯", "蓉城", "国安", "泰山", "海港", "申花", "英博", "三镇", "海牛"],
        "intent_keywords": ["中超热点最新", "中超积分榜走势", "国足比赛复盘", "足协杯赛果", "中超争冠主线", "国内足球新闻"],
    },
    {
        "slug": "nba-hot",
        "label": "NBA热点",
        "description": "聚合 NBA、季后赛、附加赛、球星表现和伤病变化，适合做赛果复盘与人物切口。",
        "topics": ["sports"],
        "keywords": ["NBA", "季后赛", "附加赛", "湖人", "勇士", "太阳", "约基奇", "东契奇", "哈登", "活塞", "魔术"],
        "intent_keywords": ["NBA热点今日", "NBA季后赛战报", "NBA球星表现", "NBA伤病消息", "NBA附加赛复盘", "NBA今日赛果"],
    },
    {
        "slug": "uefa-champions-league-hot",
        "label": "欧冠热点",
        "description": "聚合欧冠、英超西甲德甲意甲强队走势和晋级出局主线。",
        "topics": ["sports"],
        "keywords": ["欧冠", "英超", "西甲", "意甲", "德甲", "阿森纳", "马竞", "巴黎", "拜仁", "皇马", "巴萨", "利物浦"],
        "intent_keywords": ["欧冠热点", "英超争冠走势", "五大联赛新闻", "皇马巴萨拜仁动态", "欧冠晋级形势", "欧洲足球战报"],
    },
    {
        "slug": "wtt-snooker-hot",
        "label": "国乒与斯诺克热点",
        "description": "聚合国乒、WTT、中国球员、斯诺克和国内选手相关热点。",
        "topics": ["sports"],
        "keywords": ["国乒", "WTT", "中国球员", "中国选手", "斯诺克", "吴宜泽", "赵心童", "郑钦文", "国羽"],
        "intent_keywords": ["国乒最新消息", "WTT赛程赛果", "斯诺克中国选手", "郑钦文比赛", "国羽赛事热点", "中国球员热点"],
    },
    {
        "slug": "esports-transfer-hot",
        "label": "电竞转会与阵容热点",
        "description": "聚合战队阵容、转会、收购、续约和俱乐部商业动作。",
        "topics": ["esports"],
        "keywords": ["转会", "阵容", "收购", "续约", "俱乐部", "战队", "重返", "选手", "资本"],
        "intent_keywords": ["电竞转会消息", "战队阵容调整", "选手续约官宣", "电竞俱乐部动态", "LPL转会期", "CS2阵容变化"],
    },
    {
        "slug": "lpl-kpl-hot",
        "label": "LPL KPL 电竞热点",
        "description": "聚合英雄联盟、王者荣耀、LPL、KPL、MSI、世界赛等赛事主线。",
        "topics": ["esports"],
        "keywords": ["LPL", "KPL", "MSI", "世界赛", "英雄联盟", "王者荣耀", "Faker", "Gumayusi", "HLE", "GEN", "JDG", "TES"],
        "intent_keywords": ["LPL热点今日", "KPL赛程战报", "英雄联盟赛事复盘", "王者荣耀比赛热点", "MSI赛况", "电竞世界杯热点"],
    },
    {
        "slug": "cs2-valorant-hot",
        "label": "CS2 无畏契约热点",
        "description": "聚合 CS2、无畏契约、VCT 和战队赛事相关动态。",
        "topics": ["esports"],
        "keywords": ["CS2", "无畏契约", "VCT", "Valorant", "5EPlay", "PRX", "T1", "XLG", "JDG"],
        "intent_keywords": ["CS2赛事热点", "无畏契约比赛", "VCT战报", "Valorant转会", "CS2战队动态", "FPS电竞新闻"],
    },
    {
        "slug": "ai-product-hot",
        "label": "AI产品热点",
        "description": "聚合 AI 工具、模型发布、产品更新、价格变化和用户实测信号。",
        "topics": ["ai", "platform"],
        "keywords": ["OpenAI", "ChatGPT", "Claude", "Gemini", "Sora", "DeepSeek", "模型", "产品", "工具", "发布", "更新"],
        "intent_keywords": ["AI产品更新", "ChatGPT最新消息", "Claude Gemini热点", "大模型发布", "AI工具推荐", "Sora DeepSeek动态"],
    },
    {
        "slug": "ai-agent-hot",
        "label": "AI智能体热点",
        "description": "聚合智能体、Agent、自动化工作流、开发者工具和落地案例。",
        "topics": ["ai", "github", "platform"],
        "keywords": ["智能体", "Agent", "agent", "automation", "自动化", "工作流", "CLI", "MCP"],
        "intent_keywords": ["AI智能体热点", "Agent工作流", "自动化工具动态", "MCP新闻", "AI Agent落地案例", "编程智能体"],
    },
    {
        "slug": "github-ai-projects",
        "label": "GitHub AI项目",
        "description": "聚合 GitHub 上升温的 AI、Agent、LLM 和开发者工具项目。",
        "topics": ["github"],
        "keywords": ["AI", "agent", "llm", "automation", "workflow", "cli", "mcp", "model", "developer"],
        "intent_keywords": ["GitHub AI项目", "开源AI工具", "LLM开源项目", "Agent开源项目", "开发者工具热点", "GitHub Trending AI"],
    },
    {
        "slug": "movie-tv-hot",
        "label": "电影剧集综艺热点",
        "description": "聚合电影、电视剧、综艺、票房、定档和口碑讨论。",
        "topics": ["entertainment"],
        "keywords": ["电影", "电视剧", "综艺", "票房", "定档", "上映", "导演", "演员", "口碑"],
        "intent_keywords": ["电影热点今日", "电视剧热搜", "综艺话题", "票房最新消息", "新片定档", "影视口碑讨论"],
    },
    {
        "slug": "platform-discussion-hot",
        "label": "平台热议热点",
        "description": "聚合 X、YouTube、微博、抖音等平台上的讨论信号，供二次传播参考。",
        "topics": ["platform"],
        "keywords": ["X", "YouTube", "微博", "抖音", "官方", "直播", "预告", "采访", "发布", "回应"],
        "intent_keywords": ["微博热搜热点", "抖音热榜", "YouTube热门视频", "X热议话题", "平台讨论趋势", "社媒热点追踪"],
    },
]
DEFAULT_SOURCE_RADAR_SOURCES = [
    {"id": "weibo", "label": "微博", "title": "实时热搜", "topic": "platform", "group": "平台热议", "column": "realtime", "type": "hottest", "interval": "2m", "quality_tier": "high", "focus_default": True, "color": "#ff4d4f"},
    {"id": "douyin", "label": "抖音", "title": "热点榜", "topic": "platform", "group": "平台热议", "column": "realtime", "type": "hottest", "interval": "5m", "quality_tier": "medium", "focus_default": True, "color": "#111114"},
    {"id": "bilibili-hot-search", "label": "哔哩哔哩", "title": "热搜", "topic": "platform", "group": "平台热议", "column": "realtime", "type": "hottest", "interval": "10m", "quality_tier": "medium", "focus_default": True, "color": "#0a84ff"},
    {"id": "hupu", "label": "虎扑", "title": "主干道热帖", "topic": "sports", "group": "体育", "column": "sports", "type": "hottest", "interval": "10m", "quality_tier": "high", "focus_default": True, "color": "#0a84ff"},
    {"id": "zhihu", "label": "知乎", "title": "热榜", "topic": "platform", "group": "平台热议", "column": "focus", "type": "hottest", "interval": "10m", "quality_tier": "medium", "focus_default": False, "color": "#1772f6"},
    {"id": "baidu", "label": "百度热搜", "title": "热搜", "topic": "platform", "group": "平台热议", "column": "realtime", "type": "hottest", "interval": "5m", "quality_tier": "medium", "focus_default": False, "color": "#2932e1"},
    {"id": "ithome", "label": "IT之家", "title": "快讯", "topic": "ai", "group": "AI/科技", "column": "tech", "type": "realtime", "interval": "10m", "quality_tier": "high", "focus_default": True, "color": "#635bff"},
    {"id": "36kr", "label": "36氪", "title": "最新", "topic": "ai", "group": "AI/科技", "column": "tech", "type": "realtime", "interval": "15m", "quality_tier": "high", "focus_default": False, "color": "#1d9bf0"},
    {"id": "github-trending-today", "label": "GitHub", "title": "Trending Today", "topic": "github", "group": "GitHub", "column": "tech", "type": "hottest", "interval": "30m", "quality_tier": "high", "focus_default": True, "color": "#34a853"},
    {"id": "producthunt", "label": "Product Hunt", "title": "热门产品", "topic": "ai", "group": "AI/科技", "column": "tech", "type": "hottest", "interval": "30m", "quality_tier": "medium", "focus_default": False, "color": "#ff6154"},
    {"id": "douban", "label": "豆瓣", "title": "热门电影", "topic": "entertainment", "group": "娱乐", "column": "entertainment", "type": "hottest", "interval": "30m", "quality_tier": "medium", "focus_default": False, "color": "#00b578"},
    {"id": "qqvideo-tv-hotsearch", "label": "腾讯视频", "title": "热搜榜", "topic": "entertainment", "group": "娱乐", "column": "entertainment", "type": "hottest", "interval": "30m", "quality_tier": "medium", "focus_default": False, "color": "#ff6a3d"},
]
SPAM_TITLE_PATTERNS = [
    re.compile(r"results\s+(?:for|on)\b", re.IGNORECASE),
    re.compile(r"posts?\s*(?:&|and)\s*updates?", re.IGNORECASE),
    re.compile(r"\b(?:\d{2,8}|[a-z0-9-]{2,})\.(?:vip|tw|top|bet|win|casino)\b", re.IGNORECASE),
    re.compile(r"IM电竞|体育博彩|百家乐|送彩金|送彩金|注册送|投注平台|开户注册|现金网|真人娱乐"),
    re.compile(r"[\"“][^\"”]{0,24}官方\s*\d{2,8}\.[a-z]{2,6}[^\"”]{0,24}[\"”]", re.IGNORECASE),
]


def is_spam_or_ad_title(title: object) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    return any(pattern.search(text) or pattern.search(compact) for pattern in SPAM_TITLE_PATTERNS)


def load_source_radar_sources() -> list[dict[str, object]]:
    try:
        payload = json.loads(SOURCE_RADAR_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return list(DEFAULT_SOURCE_RADAR_SOURCES)

    raw_sources = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(raw_sources, list):
        return list(DEFAULT_SOURCE_RADAR_SOURCES)

    defaults = {str(source.get("id")): dict(source) for source in DEFAULT_SOURCE_RADAR_SOURCES if source.get("id")}
    sources: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("id") or "").strip()
        if not source_id or source_id in seen or raw.get("enabled") is False:
            continue
        merged = {**defaults.get(source_id, {}), **raw}
        if not merged.get("label") or not merged.get("title"):
            continue
        merged.setdefault("topic", "platform")
        merged.setdefault("group", "平台热议")
        merged.setdefault("column", "focus")
        merged.setdefault("type", "hottest")
        merged.setdefault("interval", "")
        merged.setdefault("quality_tier", "normal")
        merged.setdefault("focus_default", False)
        merged.setdefault("color", "#0071e3")
        sources.append(merged)
        seen.add(source_id)
    return sources or list(DEFAULT_SOURCE_RADAR_SOURCES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch, rank, and export daily multi-topic hotspots.")
    parser.add_argument("--date", default=None, help="YYYYMMDD，例如 20260418；默认今天。")
    parser.add_argument("--output-dir", default="output", help="Directory for ranked outputs.")
    parser.add_argument("--sources-dir", default="sources", help="Directory for fetched raw source files.")
    parser.add_argument("--top", type=int, default=20, help="How many ranked hotspot rows to export per topic.")
    parser.add_argument("--min-score", type=float, default=5.8, help="Minimum total_score to keep in the final export.")
    parser.add_argument(
        "--reference-time",
        help="ISO-8601 reference timestamp used for scoring. Defaults to local current time.",
    )
    return parser.parse_args()


def strip_html(text: str) -> str:
    cleaned = unescape(str(text or ""))
    cleaned = re.sub(r"<\s*(?:br|/p|/div|/li)\s*/?>", "。", cleaned, flags=re.IGNORECASE)
    cleaned = HTML_TAG_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def clean_summary(text: str, title: str = "", source: str | None = None) -> str:
    cleaned = strip_html(text)
    if not cleaned:
        return ""
    if title and cleaned.startswith(title):
        cleaned = cleaned[len(title):].strip(" -|｜。:：")
    if source:
        cleaned = re.sub(rf"(?:^|\s){re.escape(source)}(?:$|\s)", " ", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|｜。:：")
    if len(cleaned) > 240:
        cleaned = cleaned[:240].rstrip("，,。 ") + "。"
    return cleaned


def load_translation_cache(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): cleanup_translated_text(str(value)) for key, value in payload.items() if value}


def save_translation_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = dict(list(cache.items())[-2000:])
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_translation_input(text: str) -> str:
    cleaned = URL_RE.sub("", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:320]


def is_probably_english(text: str) -> bool:
    cleaned = clean_translation_input(text)
    if not cleaned:
        return False
    letters = len(ENGLISH_RE.findall(cleaned))
    cjk_count = len(CJK_RE.findall(cleaned))
    words = re.findall(r"[A-Za-z]{2,}", cleaned)
    return letters >= 12 and len(words) >= 3 and (cjk_count == 0 or letters >= cjk_count * 2)


def parse_translation_payload(payload: object) -> str:
    if not isinstance(payload, list) or not payload:
        return ""
    rows = payload[0]
    if not isinstance(rows, list):
        return ""
    parts: list[str] = []
    for row in rows:
        if isinstance(row, list) and row and isinstance(row[0], str):
            parts.append(row[0])
    return "".join(parts).strip()


def fallback_translate_en_to_zh(text: str) -> str:
    translated = clean_translation_input(text)
    if not translated:
        return ""
    ordered = sorted(TRANSLATION_FALLBACKS.items(), key=lambda item: len(item[0]), reverse=True)
    for source, target in ordered:
        translated = re.sub(rf"\b{re.escape(source)}\b", target, translated, flags=re.IGNORECASE)
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated


def cleanup_translated_text(text: str) -> str:
    cleaned = clean_translation_input(strip_html(text))
    for source, target in TRANSLATION_POST_FIXES.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace(" | ", "｜")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def translate_text_zh(text: str, cache: dict[str, str]) -> str:
    cleaned = clean_translation_input(text)
    if not is_probably_english(cleaned):
        return cleanup_translated_text(fallback_translate_en_to_zh(cleaned) or str(text or ""))
    cached = cache.get(cleaned)
    if cached:
        cache[cleaned] = cleanup_translated_text(cached)
        return cache[cleaned]

    base_text = fallback_translate_en_to_zh(cleaned) or cleaned
    translated = ""
    try:
        response = requests.get(
            TRANSLATE_API_URL,
            params={"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": base_text},
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        translated = parse_translation_payload(response.json())
    except Exception:
        translated = ""

    if not translated:
        translated = base_text

    cache[cleaned] = cleanup_translated_text(translated or cleaned)
    return cache[cleaned]


def localize_platform_items(items: list[dict[str, object]], cache: dict[str, str]) -> list[dict[str, object]]:
    for item in items:
        topic = str(item.get("topic") or "")
        if topic not in PLATFORM_TOPICS:
            continue

        title = str(item.get("title") or "").strip()
        summary = clean_translation_input(str(item.get("summary") or ""))

        if title and is_probably_english(title):
            item["original_title"] = title
            item["translated_title"] = translate_text_zh(title, cache)
        if summary and is_probably_english(summary):
            item["original_summary"] = summary
            item["translated_summary"] = translate_text_zh(summary, cache)
    return items


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


def decode_google_news_article_url(url: object) -> str:
    text_url = str(url or "").strip()
    if "news.google.com/rss/articles/" not in text_url:
        return text_url
    token = text_url.split("/articles/", 1)[-1].split("?", 1)[0].strip()
    if not token:
        return ""
    try:
        padded = token + "=" * ((4 - len(token) % 4) % 4)
        decoded = base64.urlsafe_b64decode(padded)
    except Exception:
        return ""
    match = re.search(rb"https?://[^\x00-\x20\"'<>]+", decoded)
    if not match:
        return ""
    try:
        return match.group(0).decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def is_google_news_url(url: object) -> bool:
    try:
        return "news.google.com" in urlparse(str(url or "")).netloc
    except Exception:
        return False


@lru_cache(maxsize=512)
def resolve_google_news_redirect(url: str, allow_network: bool = True) -> str:
    text_url = str(url or "").strip()
    if not text_url or not is_google_news_url(text_url):
        return text_url
    decoded = decode_google_news_article_url(text_url)
    if decoded and not is_google_news_url(decoded):
        return decoded
    if not allow_network:
        return ""
    if os.environ.get("HOTSPOT_RESOLVE_GOOGLE_NEWS", "1").strip() in {"0", "false", "False"}:
        return ""
    try:
        timeout = float(os.environ.get("HOTSPOT_GOOGLE_RESOLVE_TIMEOUT", "2.5"))
        response = requests.get(text_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        final_url = str(response.url or "").strip()
    except Exception:
        return ""
    if final_url and not is_google_news_url(final_url):
        return final_url
    return ""


def resolve_reference_url(link: object, source_url: object = None, allow_network: bool = True) -> str:
    text_link = str(link or "").strip()
    if not text_link:
        return str(source_url or "").strip()
    if is_google_news_url(text_link):
        resolved = resolve_google_news_redirect(text_link, allow_network=allow_network)
        return resolved or text_link
    return text_link


def google_network_resolve_allowed() -> bool:
    global GOOGLE_NEWS_NETWORK_RESOLVE_USED
    try:
        limit = max(0, int(os.environ.get("HOTSPOT_GOOGLE_RESOLVE_LIMIT_PER_RUN", "8")))
    except ValueError:
        limit = 8
    if GOOGLE_NEWS_NETWORK_RESOLVE_USED >= limit:
        return False
    GOOGLE_NEWS_NETWORK_RESOLVE_USED += 1
    return True


def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def clean_public_title(title: str) -> str:
    cleaned = strip_html(title)
    cleaned = ESPORTS_SOURCE_SUFFIX_RE.sub("", cleaned)
    cleaned = re.sub(
        r"\s*[-—]\s*(?:Score[-—]?电竞玩家赛事社区|scoregg\.com|遥远的布莱梅|木质烧杯)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" -|｜")


def source_radar_headers() -> dict[str, str]:
    return {
        **HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{SOURCE_RADAR_API}/",
        "Origin": SOURCE_RADAR_API,
    }


def source_radar_timestamp(value: object) -> str:
    try:
        seconds = float(value) / 1000
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(seconds, tz=dt.timezone.utc).astimezone().replace(second=0, microsecond=0).isoformat()


def normalize_source_radar_item(
    raw_item: dict[str, object],
    source: dict[str, object],
    rank: int,
    translation_cache: dict[str, str] | None = None,
) -> dict[str, object] | None:
    raw_title = clean_public_title(str(raw_item.get("title") or ""))
    if not raw_title or is_spam_or_ad_title(raw_title):
        return None
    title = raw_title
    if is_probably_english(title):
        title = translate_text_zh(title, translation_cache if translation_cache is not None else {})

    extra = raw_item.get("extra") if isinstance(raw_item.get("extra"), dict) else {}
    hot_value = str(extra.get("info") or raw_item.get("hot") or raw_item.get("extraText") or "").strip()
    hover = str(extra.get("hover") or raw_item.get("summary") or raw_item.get("description") or "").strip()
    summary = clean_summary(hover, title=raw_title, source=source.get("label"))
    if summary and is_probably_english(summary):
        summary = translate_text_zh(summary, translation_cache if translation_cache is not None else {})

    url = str(raw_item.get("url") or "").strip()
    if url.startswith("/"):
        url = f"{SOURCE_RADAR_API}{url}"

    item: dict[str, object] = {
        "rank": rank,
        "id": str(raw_item.get("id") or url or normalize_title(raw_title)),
        "title": title,
        "url": url,
        "source_id": str(source["id"]),
        "source_label": str(source["label"]),
        "source_title": str(source["title"]),
        "topic": str(source["topic"]),
        "group": str(source["group"]),
    }
    if hot_value:
        item["hot_value"] = hot_value
    if summary:
        item["summary"] = summary
    if title != raw_title:
        item["original_title"] = raw_title
    return item


def source_radar_cache_path(source_id: object) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(source_id or "source")).strip("-") or "source"
    return SOURCE_RADAR_CACHE_DIR / f"{safe}.json"


def load_cached_source_radar_card(source_id: object) -> dict[str, object] | None:
    path = source_radar_cache_path(source_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or not payload.get("items"):
        return None
    payload = dict(payload)
    payload["status"] = "cache"
    payload["cache_used"] = True
    payload.setdefault("cached_at", path.stat().st_mtime)
    return payload


def write_cached_source_radar_card(card: dict[str, object]) -> None:
    source_id = card.get("id")
    if not source_id or not card.get("items"):
        return
    SOURCE_RADAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(card)
    payload["cached_at"] = datetime.now().astimezone().isoformat()
    payload["cache_version"] = 1
    write_json(source_radar_cache_path(source_id), payload)


def fetch_source_radar_source(
    source: dict[str, object],
    translation_cache: dict[str, str] | None = None,
    limit: int = 20,
) -> dict[str, object]:
    card: dict[str, object] = {
        "id": str(source["id"]),
        "label": str(source["label"]),
        "title": str(source["title"]),
        "topic": str(source["topic"]),
        "group": str(source["group"]),
        "column": str(source.get("column") or "focus"),
        "feed_type": str(source.get("type") or "hottest"),
        "interval": str(source.get("interval") or ""),
        "quality_tier": str(source.get("quality_tier") or "normal"),
        "focus_default": bool(source.get("focus_default")),
        "home": str(source.get("home") or ""),
        "color": str(source.get("color") or "#0071e3"),
        "status": "error",
        "updated_at": "",
        "item_count": 0,
        "items": [],
    }
    try:
        response = requests.get(
            f"{SOURCE_RADAR_API}/api/s",
            params={"id": source["id"]},
            headers=source_radar_headers(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        cached = load_cached_source_radar_card(source.get("id"))
        if cached is not None:
            cached["error"] = str(exc)
            cached["status"] = "cache"
            cached["cache_reason"] = "provider_failed"
            return cached
        card["error"] = str(exc)
        return card

    if not isinstance(payload, dict):
        cached = load_cached_source_radar_card(source.get("id"))
        if cached is not None:
            cached["error"] = "invalid payload"
            cached["status"] = "cache"
            cached["cache_reason"] = "provider_invalid_payload"
            return cached
        card["error"] = "invalid payload"
        return card

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raw_items = []

    items: list[dict[str, object]] = []
    for rank, raw_item in enumerate(raw_items[:limit], 1):
        if not isinstance(raw_item, dict):
            continue
        item = normalize_source_radar_item(raw_item, source, rank, translation_cache)
        if item is not None:
            items.append(item)

    card.update(
        {
            "status": str(payload.get("status") or "success"),
            "updated_at": source_radar_timestamp(payload.get("updatedTime")),
            "item_count": len(raw_items),
            "items": items,
        }
    )
    write_cached_source_radar_card(card)
    return card


def build_source_radar_payload(reference_time: datetime, translation_cache: dict[str, str] | None = None) -> dict[str, object]:
    configured_sources = load_source_radar_sources()
    sources = [fetch_source_radar_source(source, translation_cache) for source in configured_sources]
    ok_sources = [source for source in sources if source.get("items")]
    topic_counts = Counter(str(item.get("topic") or "") for source in ok_sources for item in source.get("items", []))
    group_counts = Counter(str(source.get("group") or "") for source in ok_sources)
    column_counts = Counter(str(source.get("column") or "") for source in ok_sources)
    try:
        cache_dir_display = str(SOURCE_RADAR_CACHE_DIR.relative_to(ROOT))
    except ValueError:
        cache_dir_display = str(SOURCE_RADAR_CACHE_DIR)
    return {
        "generated_at": reference_time.isoformat(),
        "provider": SOURCE_RADAR_API,
        "provider_mode": "newsnow_with_local_source_cache",
        "cache_dir": cache_dir_display,
        "source_count": len(sources),
        "ok_count": len(ok_sources),
        "item_count": sum(len(source.get("items", [])) for source in ok_sources),
        "topic_counts": dict(topic_counts),
        "group_counts": dict(group_counts),
        "column_counts": dict(column_counts),
        "config_path": str(SOURCE_RADAR_CONFIG_PATH.relative_to(ROOT)) if SOURCE_RADAR_CONFIG_PATH.exists() else "",
        "sources": sources,
    }


def source_radar_is_usable(payload: dict[str, object] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        ok_count = int(payload.get("ok_count") or 0)
    except (TypeError, ValueError):
        ok_count = 0
    return ok_count > 0 and isinstance(payload.get("sources"), list)


def load_source_radar_fallback(path: Path) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    if path.exists():
        try:
            local_payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(local_payload, dict):
                candidates.append(local_payload)
        except Exception:
            pass
    fallback_url = os.environ.get("HOTSPOT_SOURCE_RADAR_FALLBACK_URL") or page_url("output/source_radar.json")
    try:
        response = requests.get(fallback_url, headers=HEADERS, timeout=8)
        response.raise_for_status()
        remote_payload = response.json()
        if isinstance(remote_payload, dict):
            candidates.append(remote_payload)
    except Exception:
        pass
    for payload in candidates:
        if source_radar_is_usable(payload):
            payload = dict(payload)
            payload["stale"] = True
            payload["stale_reason"] = "source_radar_provider_failed; kept last usable payload"
            payload["stale_checked_at"] = datetime.now().astimezone().isoformat()
            return payload
    return None


def write_source_radar_payload(
    output_dir: Path,
    reference_time: datetime,
    translation_cache: dict[str, str] | None = None,
) -> Path:
    path = output_dir / "source_radar.json"
    payload = build_source_radar_payload(reference_time, translation_cache)
    if not source_radar_is_usable(payload):
        fallback = load_source_radar_fallback(path)
        if fallback is not None:
            payload = fallback
    write_json(path, payload)
    return path


def build_source_quality_payload(
    ranked_payload: dict[str, object],
    windows_payload: dict[str, object],
    source_radar_payload: dict[str, object] | None,
    reference_time: datetime,
) -> dict[str, object]:
    stats: dict[str, dict[str, object]] = {}

    def ensure_source(name: str) -> dict[str, object]:
        key = name.strip() or "未知来源"
        if key not in stats:
            stats[key] = {
                "source": key,
                "selected_count": 0,
                "seven_day_count": 0,
                "score_sum": 0.0,
                "max_score": 0.0,
                "topics": Counter(),
                "domains": Counter(),
                "sample_titles": [],
            }
        return stats[key]

    def add_item(item: dict[str, object], seven_day: bool = False) -> None:
        rows = item.get("sources") if isinstance(item.get("sources"), list) else []
        if rows:
            source_names = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                source_names.append(str(row.get("source") or row.get("name") or item.get("source") or "未知来源"))
        else:
            source_names = [str(item.get("source") or "未知来源")]
        score = float(item.get("window_score", item.get("total_score", item.get("score", 0))) or 0)
        topic = str(item.get("topic") or "")
        domain_name = item_source_domain(item)
        title = str(item.get("title") or "")
        for source_name in dict.fromkeys(source_names):
            bucket = ensure_source(source_name)
            if seven_day:
                bucket["seven_day_count"] = int(bucket["seven_day_count"]) + 1
            else:
                bucket["selected_count"] = int(bucket["selected_count"]) + 1
                bucket["score_sum"] = float(bucket["score_sum"]) + score
                bucket["max_score"] = max(float(bucket["max_score"]), score)
            if topic:
                bucket["topics"][topic] += 1
            if domain_name:
                bucket["domains"][domain_name] += 1
            samples = bucket["sample_titles"]
            if isinstance(samples, list) and title and title not in samples and len(samples) < 5:
                samples.append(title)

    for raw in ranked_payload.get("items") or []:
        if isinstance(raw, dict):
            add_item(raw, seven_day=False)

    seven_day_items = (((windows_payload.get("windows") or {}).get("7d") or {}).get("items") or [])
    for raw in seven_day_items:
        if isinstance(raw, dict):
            add_item(raw, seven_day=True)

    if source_radar_payload and isinstance(source_radar_payload.get("sources"), list):
        for source in source_radar_payload.get("sources") or []:
            if not isinstance(source, dict):
                continue
            label = str(source.get("label") or source.get("id") or "未知来源")
            bucket = ensure_source(label)
            bucket["radar_status"] = source.get("status")
            bucket["radar_item_count"] = int(source.get("item_count") or 0)
            bucket["radar_display_count"] = len(source.get("items") or []) if isinstance(source.get("items"), list) else 0
            bucket["radar_updated_at"] = source.get("updated_at") or ""

    rows: list[dict[str, object]] = []
    for bucket in stats.values():
        selected_count = int(bucket.pop("selected_count"))
        score_sum = float(bucket.pop("score_sum"))
        avg_score = round(score_sum / selected_count, 2) if selected_count else 0.0
        topics = bucket.pop("topics")
        domains = bucket.pop("domains")
        rows.append(
            {
                **bucket,
                "selected_count": selected_count,
                "avg_score": avg_score,
                "max_score": round(float(bucket.get("max_score") or 0), 2),
                "topics": dict(topics.most_common()),
                "domains": dict(domains.most_common(5)),
                "quality_hint": source_quality_hint(selected_count, avg_score, int(bucket.get("radar_display_count") or 0)),
            }
        )
    rows.sort(key=lambda row: (-int(row.get("selected_count") or 0), -float(row.get("avg_score") or 0), str(row.get("source") or "")))
    return {
        "generated_at": reference_time.isoformat(),
        "source_count": len(rows),
        "selected_item_count": len([item for item in ranked_payload.get("items") or [] if isinstance(item, dict)]),
        "sources": rows,
    }


def source_quality_hint(selected_count: int, avg_score: float, radar_display_count: int) -> str:
    if selected_count >= 5 and avg_score >= 7:
        return "高信号来源，适合继续保留和加权。"
    if selected_count == 0 and radar_display_count >= 10:
        return "有热榜产出但主榜入选少，适合作为旁路参考。"
    if selected_count <= 1 and avg_score < 6.5:
        return "低频或低分来源，后续可观察是否降权。"
    return "正常来源，继续观察稳定性。"


def write_source_quality_payload(
    output_dir: Path,
    ranked_payload: dict[str, object],
    windows_payload: dict[str, object],
    source_radar_payload: dict[str, object] | None,
    reference_time: datetime,
) -> Path:
    path = output_dir / "source_quality.json"
    write_json(path, build_source_quality_payload(ranked_payload, windows_payload, source_radar_payload, reference_time))
    return path


def should_skip(title: str, source: str | None) -> bool:
    if len(title.strip()) <= 4:
        return True
    if is_spam_or_ad_title(title):
        return True
    if source:
        lowered_source = source.strip().lower()
        if any(flag in lowered_source for flag in {"facebook", "腾讯体育社区", "新浪", "手机新浪"}):
            return True
        if lowered_source in {"腾讯体育社区", "新浪网"}:
            return True
    lowered_title = title.lower()
    if any(flag in lowered_title for flag in ["_新浪新闻", "_手机新浪网"]):
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
        re.compile(r"results\s+for\s+[\"“]", re.IGNORECASE),
        re.compile(r"results\s+on\s+x", re.IGNORECASE),
        re.compile(r"posts?\s*(?:&|and)\s*updates?", re.IGNORECASE),
        re.compile(r"[｛{]\s*官网\s*[：:]", re.IGNORECASE),
        re.compile(r"官网\s*[：:]", re.IGNORECASE),
        re.compile(r"\b\d{2,6}\.tw\b", re.IGNORECASE),
        re.compile(r"\b(?:\d{2,6}|[a-z0-9-]{2,})\.tw[｝}，,\.\s]", re.IGNORECASE),
        re.compile(r"\b(?:\d{2,8}|[a-z0-9-]{2,})\.(?:vip|top|bet|win|casino)\b", re.IGNORECASE),
        re.compile(r"百家乐|博彩|注册送|投注平台|开户注册"),
        re.compile(r"视频集锦"),
        re.compile(r"集锦"),
        re.compile(r"比赛回顾"),
        re.compile(r"回放"),
        re.compile(r"录像"),
        re.compile(r"赛程表"),
        re.compile(r"比赛中心"),
        re.compile(r"文字实录"),
        re.compile(r"图文直播"),
        re.compile(r"即时比分"),
        re.compile(r"官方网站"),
        re.compile(r"官方平台"),
        re.compile(r"官方入口"),
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


def low_value_title(title: str) -> bool:
    lowered = str(title or "").lower()
    if is_spam_or_ad_title(title):
        return True
    blocked = [
        "赛程表",
        "比赛中心",
        "文字实录",
        "图文直播",
        "即时比分",
        "全自动",
        "彻底取代",
        "订阅登录",
        "都在用",
        "工作流教程",
        "保姆级",
        "炸了",
        "疯了",
        "太敢说",
        "彻底沦为过去式",
        "太离谱",
        "直接傻眼",
        "看完直接傻眼",
        "multi sub",
        "cctv电视剧",
        "iqiyi",
        "大电影",
        "动作 历史 战争",
        "盗墓",
        "毒狼",
        "护国良相",
        "外交命案",
        "美股",
        "股价",
        "盘后",
        "财经焦点",
        "比索",
        "川普",
        "特斯拉",
        "从零开始",
        "跑通",
        "星洲日报",
        "sinchew",
        "电影大剧院",
        "full《",
        "经典武侠动作港片",
        "chinese film",
        "apec",
        "女性友好",
        "国家档案局",
        "司法应用指南",
        "食品产业",
        "产业发展与安全",
        "支持采购大模型",
        "国务院：加强6g",
        "应用试点",
        "示范应用",
        "产业大会",
        "首映式",
        "北影节",
        "北京国际电影节",
        "圆桌会",
        "创作营",
        "中国电影博物馆",
        "沪游双周报",
        "嘉年华",
        "results for",
        "results on x",
        "posts & updates",
        "posts and updates",
        "｛官网",
        "{官网",
        "官网：",
        "官网:",
        "701.tw",
        "852.tw",
        ".vip",
        "im电竞",
        "百家乐",
        "博彩",
        "注册送",
        "投注平台",
        "开户注册",
    ]
    return any(token.lower() in lowered for token in blocked) or lowered.count("!") + lowered.count("！") >= 2


def platform_title_has_keep_signal(title: str) -> bool:
    return bool(PLATFORM_KEEP_SIGNAL_RE.search(str(title or "")))


def platform_video_noise_title(title: str) -> bool:
    text = str(title or "")
    if not text.strip():
        return False
    if not PLATFORM_VIDEO_NOISE_RE.search(text):
        return False
    return not platform_title_has_keep_signal(text)


def low_value_item_title(topic: str, title: str) -> bool:
    if low_value_title(title):
        return True
    compact = re.sub(r"\s+", "", str(title or ""))
    normalized_topic = "platform" if topic in PLATFORM_TOPICS else topic
    if normalized_topic == "platform":
        if platform_video_noise_title(title):
            return True
        if len(compact) > 96:
            return True
        if "wtt" in title.lower() and any(
            token in title
            for token in ("支线赛", "第一节", "第二节", "WD Final", "WS SF", "MS SF", "MD Final", "XD Final", "T4｜Q")
        ):
            return True
    return False


def query_matches_title(title: str, spec: dict) -> bool:
    required_keywords = spec.get("required_keywords")
    if not isinstance(required_keywords, list) or not required_keywords:
        return True
    lowered_title = title.lower()
    for keyword in required_keywords:
        lowered_keyword = str(keyword).lower().strip()
        if not lowered_keyword:
            continue
        if CJK_RE.search(lowered_keyword):
            if lowered_keyword in lowered_title:
                return True
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(lowered_keyword)}(?![a-z0-9])", lowered_title):
            return True
    return False


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
    try:
        network_resolve_limit = max(0, int(os.environ.get("HOTSPOT_GOOGLE_RESOLVE_LIMIT_PER_FEED", "2")))
    except ValueError:
        network_resolve_limit = 2
    network_resolve_count = 0
    for item in root.findall("./channel/item"):
        source_el = item.find("source")
        source_name = source_el.text.strip() if source_el is not None and source_el.text else None
        if not source_name:
            source_name = str(spec.get("default_source") or "").strip() or None
        title = clean_public_title(split_title(unescape(item.findtext("title", "").strip()), source_name))
        description = clean_summary(text(item.find("description")), title=title, source=source_name)
        if not title or should_skip(title, source_name) or low_value_item_title(str(spec.get("topic") or ""), title):
            continue
        if not query_matches_title(f"{title} {description}", spec):
            continue

        published_at = parse_pubdate(item.findtext("pubDate", ""))
        link = item.findtext("link", "").strip() or None
        source_url = source_el.attrib.get("url") if source_el is not None else None
        allow_network_resolve = True
        if is_google_news_url(link) and not decode_google_news_article_url(link):
            allow_network_resolve = network_resolve_count < network_resolve_limit and google_network_resolve_allowed()
            if allow_network_resolve:
                network_resolve_count += 1
        reference_url = resolve_reference_url(link, source_url, allow_network=allow_network_resolve)

        items.append(
            {
                "title": title,
                "summary": description,
                "source": source_name,
                "url": reference_url,
                "google_news_url": link if link and reference_url != link else "",
                "source_url": source_url,
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
    github_token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def as_reference_timezone(value: datetime | None, reference_time: datetime) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=reference_time.tzinfo)
    return value.astimezone(reference_time.tzinfo)


def history_snapshot_time(payload: dict[str, object], path: Path, reference_time: datetime) -> datetime | None:
    snapshot = parse_ranked_timestamp(payload.get("reference_time"))
    if snapshot is not None:
        return as_reference_timezone(snapshot, reference_time)
    run_date = payload.get("run_date")
    if isinstance(run_date, str) and run_date:
        try:
            return datetime.fromisoformat(f"{run_date}T12:00:00").replace(tzinfo=reference_time.tzinfo)
        except ValueError:
            pass
    match = re.match(r"(\d{8})(T\d{6})?_hotspots_ranked\.json$", path.name)
    if match:
        stamp = match.group(1) + (match.group(2) or "T120000")
        try:
            return datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=reference_time.tzinfo)
        except ValueError:
            return None
    return None


def source_rows(item: dict[str, object]) -> list[dict[str, str]]:
    rows = item.get("sources")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def merge_source_rows(left: list[dict[str, str]], right: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen = set()
    for row in left + right:
        source_name = str(row.get("source") or row.get("name") or "").strip()
        title = clean_public_title(str(row.get("title") or ""))
        url = str(row.get("url") or "").strip()
        key = (source_name.lower(), title.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "source": source_name,
                "title": title,
                "url": url,
                "domain": row.get("domain") or "",
            }
        )
    return merged


def is_history_file(path: Path) -> bool:
    if path.name.startswith(("latest_", "sample_", "real_")):
        return False
    return bool(re.match(r"^\d{8}(T\d{6})?_hotspots_ranked\.json$", path.name))


def build_window_items(history_payloads: list[tuple[datetime, dict[str, object]]], window_days: int, top: int, reference_time: datetime) -> list[dict[str, object]]:
    threshold = reference_time - timedelta(days=window_days)
    aggregated: dict[tuple[str, str], dict[str, object]] = {}

    for snapshot_time, payload in history_payloads:
        if snapshot_time < threshold:
            continue
        items = payload.get("items")
        if not isinstance(items, list):
            continue
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            topic = str(raw_item.get("topic") or "sports")
            cleaned_title = clean_public_title(str(raw_item.get("title") or ""))
            display_title = str(raw_item.get("repo") or "").strip() if topic == "github" and raw_item.get("repo") else cleaned_title
            if not display_title or low_value_item_title(topic, display_title):
                continue
            semantic_key = semantic_event_key(raw_item, display_title)
            key = (topic, semantic_key or normalize_title(display_title))
            base_score = float(raw_item.get("total_score", raw_item.get("score", 0)) or 0)
            source_name = str(raw_item.get("source") or "")
            blocked = source_name.lower()
            if any(flag in blocked for flag in ("新浪", "手机新浪", "facebook", "腾讯体育社区")):
                continue
            if str(raw_item.get("topic_type") or "").endswith("low_value"):
                continue
            if key not in aggregated:
                item = dict(raw_item)
                item["title"] = display_title
                if item.get("summary"):
                    item["summary"] = clean_summary(str(item.get("summary") or ""), title=display_title, source=source_name)
                if display_title != cleaned_title and cleaned_title:
                    item["original_title"] = cleaned_title
                item["window_days"] = window_days
                item["appearance_count"] = 0
                item["first_seen_at"] = snapshot_time.isoformat()
                item["last_seen_at"] = snapshot_time.isoformat()
                item["history_dates"] = []
                item["window_score"] = base_score
                item["_max_total_score"] = base_score
                item["_score_sum"] = 0.0
                item["_sources"] = source_rows(raw_item)
                aggregated[key] = item

            target = aggregated[key]
            target["appearance_count"] += 1
            target["_score_sum"] += base_score
            target["last_seen_at"] = max(str(target["last_seen_at"]), snapshot_time.isoformat())
            target["first_seen_at"] = min(str(target["first_seen_at"]), snapshot_time.isoformat())
            date_label = snapshot_time.strftime("%Y-%m-%d %H:%M")
            if date_label not in target["history_dates"]:
                target["history_dates"].append(date_label)
            target["_sources"] = merge_source_rows(target["_sources"], source_rows(raw_item))
            if base_score >= float(target["_max_total_score"]):
                target["_max_total_score"] = base_score
                for field in (
                    "source",
                    "url",
                    "reference_url",
                    "topic_type",
                    "storyline_tags",
                    "keyword_hits",
                    "league_tags",
                    "entity_tags",
                    "score_breakdown",
                    "why_hot",
                    "published_at",
                    "latest_published_at",
                    "repo",
                    "stars",
                    "forks",
                    "language",
                    "created_at",
                    "recommend_reason",
                    "raw_summary",
                    "event_key",
                    "llm_editorial",
                    "seo_keywords",
                ):
                    if field in raw_item:
                        target[field] = raw_item.get(field)

    grouped: dict[str, list[dict[str, object]]] = {}
    for item in aggregated.values():
        appearance_count = int(item["appearance_count"])
        last_seen = parse_ranked_timestamp(item["last_seen_at"])
        last_seen = as_reference_timezone(last_seen, reference_time)
        recency_bonus = 0.0
        if last_seen is not None:
            age_hours = (reference_time - last_seen).total_seconds() / 3600
            if age_hours <= 24:
                recency_bonus = 0.8
            elif age_hours <= 72:
                recency_bonus = 0.4
        avg_score = float(item["_score_sum"]) / max(appearance_count, 1)
        window_score = min(
            10.0,
            float(item["_max_total_score"]) * 0.28
            + avg_score * 0.52
            + min(1.8, max(0, appearance_count - 1) * 0.45)
            + recency_bonus
            + min(0.5, max(0, len(item["_sources"]) - 1) * 0.15),
        )
        item["window_score"] = round(window_score, 2)
        item["score"] = item["window_score"]
        item["total_score"] = item["window_score"]
        item["source_count"] = len(item["_sources"]) or int(item.get("source_count") or 0)
        item["sources"] = item["_sources"]
        if not item.get("source_domain"):
            item["source_domain"] = item_source_domain(item) or url_domain(item.get("reference_url") or item.get("url") or "")
        item["history_dates"] = item["history_dates"][:8]
        item["why_hot"] = list(dict.fromkeys(list(item.get("why_hot") or []) + [f"{window_days}天内出现{appearance_count}次"]))[:6]
        enrich_item_for_publication(item)
        grouped.setdefault(str(item.get("topic") or "sports"), []).append(item)

    final: list[dict[str, object]] = []
    for topic in ALL_TOPICS:
        arr = grouped.get(topic, [])
        arr.sort(
            key=lambda item: (
                item.get("pin_rank") is None,
                item.get("pin_rank", 9999),
                -float(item.get("window_score", 0)),
                str(item.get("last_seen_at") or ""),
            )
        )
        final.extend(arr[:top])

    for item in final:
        item.pop("_max_total_score", None)
        item.pop("_score_sum", None)
        item.pop("_sources", None)
    return final


def build_window_payloads(output_dir: Path, ranked_payload: dict[str, object], reference_time: datetime, top: int) -> dict[str, object]:
    history_payloads: list[tuple[datetime, dict[str, object]]] = []
    seen_paths = set()
    candidates = list((output_dir / "snapshots").glob("*_hotspots_ranked.json")) if (output_dir / "snapshots").exists() else []
    candidates.extend(path for path in output_dir.glob("*_hotspots_ranked.json") if is_history_file(path))
    latest_snapshot_time = parse_ranked_timestamp(ranked_payload.get("reference_time")) or reference_time
    history_payloads.append((as_reference_timezone(latest_snapshot_time, reference_time) or reference_time, ranked_payload))

    for path in sorted(candidates):
        if path in seen_paths or not path.exists():
            continue
        seen_paths.add(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        snapshot_time = history_snapshot_time(payload, path, reference_time)
        if snapshot_time is None:
            continue
        if snapshot_time < reference_time - timedelta(days=8):
            continue
        history_payloads.append((snapshot_time, payload))

    deduped: dict[tuple[str, str], tuple[datetime, dict[str, object]]] = {}
    for snapshot_time, payload in history_payloads:
        key = (str(payload.get("run_date") or ""), str(payload.get("reference_time") or snapshot_time.isoformat()))
        prev = deduped.get(key)
        if prev is None or snapshot_time > prev[0]:
            deduped[key] = (snapshot_time, payload)
    ordered_history = sorted(deduped.values(), key=lambda item: item[0], reverse=True)

    windows: dict[str, object] = {}
    for spec in WINDOW_SPECS:
        window_items = build_window_items(ordered_history, spec["days"], top, reference_time)
        windows[spec["key"]] = {
            "label": spec["label"],
            "days": spec["days"],
            "items": window_items,
            "topic_counts": dict(Counter(item.get("topic") for item in window_items)),
        }
    return {
        "generated_at": reference_time.isoformat(),
        "available_windows": WINDOW_SPECS,
        "windows": windows,
    }


def compact_window_payload(windows_payload: dict[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {
        "generated_at": windows_payload.get("generated_at"),
        "available_windows": windows_payload.get("available_windows") or WINDOW_SPECS,
        "windows": {},
    }
    windows = windows_payload.get("windows")
    if not isinstance(windows, dict):
        return compact
    for key, value in windows.items():
        if not isinstance(value, dict):
            continue
        items = value.get("items")
        compact["windows"][key] = {
            "label": value.get("label"),
            "days": value.get("days"),
            "topic_counts": value.get("topic_counts") or {},
            "item_count": len(items) if isinstance(items, list) else 0,
        }
    return compact


def write_split_topic_payloads(output_dir: Path, ranked_payload: dict[str, object], windows_payload: dict[str, object]) -> Path:
    topic_dir = output_dir / "topics"
    topic_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated_at": windows_payload.get("generated_at") or ranked_payload.get("reference_time"),
        "run_date": ranked_payload.get("run_date"),
        "default_window": "7d",
        "default_topic": "sports",
        "available_windows": windows_payload.get("available_windows") or WINDOW_SPECS,
        "topics": [{"key": topic, "label": ranked_payload.get("topic_labels", {}).get(topic) or topic} for topic in ALL_TOPICS],
        "source_radar": "source_radar.json",
        "source_quality": "source_quality.json",
        "daily_brief": "latest_daily_brief.json",
        "health": "health.json",
        "llm_editorial": "llm_editorial_status.json",
        "ai_context": "../ai-context.txt",
        "static_home": "../home.html",
        "pwa_manifest": "../site.webmanifest",
        "windows": {},
    }

    for spec in WINDOW_SPECS:
        window_key = spec["key"]
        window_data = (windows_payload.get("windows") or {}).get(window_key) or {}
        items = window_data.get("items") if isinstance(window_data, dict) else []
        grouped: dict[str, list[dict[str, object]]] = {topic: [] for topic in ALL_TOPICS}
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                enrich_item_for_publication(item)
                topic = str(item.get("topic") or "sports")
                if topic in grouped:
                    grouped[topic].append(item)
        files: dict[str, str] = {}
        for topic in ALL_TOPICS:
            rel_path = f"topics/{window_key}_{topic}.json"
            payload = {
                "generated_at": manifest["generated_at"],
                "run_date": ranked_payload.get("run_date"),
                "window": window_key,
                "window_label": spec["label"],
                "topic": topic,
                "topic_label": ranked_payload.get("topic_labels", {}).get(topic) or topic,
                "item_count": len(grouped[topic]),
                "items": grouped[topic],
            }
            write_json(topic_dir / f"{window_key}_{topic}.json", payload)
            files[topic] = rel_path
        manifest["windows"][window_key] = {
            "label": spec["label"],
            "days": spec["days"],
            "topic_counts": dict(window_data.get("topic_counts") or {}),
            "files": files,
        }

    manifest_path = output_dir / "latest_hotspots_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def page_url(path: str) -> str:
    return f"{SITE_BASE_URL}/{path.lstrip('/')}"


def topic_page_name(topic: str, window_key: str) -> str:
    slug = TOPIC_SLUGS.get(topic, topic)
    if window_key == "7d":
        return f"{slug}.html"
    return f"{slug}-{WINDOW_SLUGS.get(window_key, window_key)}.html"


def item_public_url(item: dict[str, object]) -> str:
    return str(item.get("reference_url") or item.get("url") or "").strip()


def item_detail_url(item: dict[str, object]) -> str:
    path = str(item.get("detail_path") or "").strip()
    return page_url(path) if path else item_public_url(item)


def stable_item_id(item: dict[str, object]) -> str:
    topic = str(item.get("topic") or "hotspot").strip().lower() or "hotspot"
    basis = "|".join(
        [
            topic,
            str(item.get("repo") or ""),
            str(item.get("title") or ""),
            str(item.get("reference_url") or item.get("url") or ""),
        ]
    )
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    return f"{topic}-{digest}"


def attach_detail_metadata(item: dict[str, object]) -> dict[str, object]:
    if not item.get("hotspot_id"):
        item["hotspot_id"] = stable_item_id(item)
    topic = str(item.get("topic") or "hotspot").strip().lower() or "hotspot"
    if not item.get("detail_path"):
        item["detail_path"] = f"hot/{topic}/{item['hotspot_id']}.html"
    if not item.get("detail_url"):
        item["detail_url"] = page_url(str(item["detail_path"]))
    return item


def content_angles(item: dict[str, object]) -> list[str]:
    topic = str(item.get("topic") or "")
    topic_type = str(item.get("topic_type") or "")
    title = str(item.get("title") or "")
    topic_label = str(item.get("topic_label") or topic)
    base: list[str]
    if topic == "sports":
        if "result" in topic_type:
            base = ["赛果复盘：结果如何改变排名、晋级线或后续对阵。", "人物切口：找出进球、绝杀、伤退或关键失误的主角。", "跟进线：下一场对阵、伤病和舆论反应是否继续发酵。"]
        elif "preview" in topic_type:
            base = ["赛前切口：阵容、伤停、主客场和历史交锋。", "内容钩子：把胜负悬念拆成一个明确问题。", "跟进线：首发名单和临场赔率变化。"]
        elif "transfer" in topic_type:
            base = ["转会切口：真假信源、合同年限和阵容位置。", "影响判断：谁会受益，谁的位置被挤压。", "跟进线：官宣、体检和记者后续确认。"]
        else:
            base = ["主线判断：先分清赛果、人物、伤病还是争议。", "内容切口：优先找国内赛事、中国球员和强队关联。", "跟进线：官方回应、后续赛程和评论区风向。"]
    elif topic == "esports":
        base = ["赛事复盘：版本、BP、团战和关键失误。", "人物切口：选手状态、续约转会或俱乐部动作。", "社区讨论：粉丝争议、解说观点和赛区排名变化。"]
    elif topic == "ai":
        base = ["产品判断：这是不是具体可用的新功能，而不只是 PR。", "行业影响：会影响创作者、开发者还是企业采购。", "跟进线：价格、开放范围、竞品反应和用户实测。"]
    elif topic == "entertainment":
        base = ["人物/作品切口：谁是传播中心，作品还是争议。", "情绪判断：评论区是支持、嘲讽还是质疑。", "跟进线：回应、票房、口碑和热搜持续时间。"]
    elif topic == "github":
        repo = str(item.get("repo") or title)
        base = [f"项目用途：先判断 {repo} 解决什么具体问题。", "开发者价值：看 stars、活跃度、语言和上手成本。", "跟进线：README、release、issue 反馈和同类项目对比。"]
    else:
        base = ["传播判断：先看是否有明确主体和二次传播空间。", "内容切口：提炼观点、金句、视频片段或评论区争议。", "跟进线：平台扩散速度和更多来源确认。"]
    why_hot = [str(v) for v in item.get("why_hot") or [] if v]
    if why_hot and len(base) < 4:
        base.append(f"热度依据：{why_hot[0]}。")
    creator = brief_creator_angle(item, topic_label).removeprefix("切口：").strip()
    if creator and creator not in base:
        base.insert(0, creator)
    return base[:4]


def editorial_summary(item: dict[str, object]) -> str:
    summary = item_summary(item)
    note = str(item.get("editor_note") or "").strip()
    hint = str(item.get("summary_hint") or "").strip()
    if summary:
        return summary
    parts = [v for v in [hint, note] if v]
    text = " ".join(parts).strip()
    if not text:
        text = "这条热点具备继续观察价值，适合结合来源、评论区和后续进展再做选题。"
    return text[:180]


def discussion_focus(item: dict[str, object]) -> list[str]:
    focus: list[str] = []
    topic = str(item.get("topic") or "")
    for key in ("keyword_hits", "entity_tags", "storyline_tags", "league_tags"):
        values = item.get(key)
        if isinstance(values, list):
            focus.extend(str(v) for v in values if v)
    if int(item.get("source_count") or 0) > 1:
        focus.append("多源交叉")
    if topic in {"sports", "esports"}:
        focus.append("赛后评论区")
    elif topic == "entertainment":
        focus.append("热搜情绪")
    elif topic == "ai":
        focus.append("用户实测")
    elif topic == "github":
        focus.append("开发者反馈")
    return list(dict.fromkeys(focus))[:8]


def numeric_score(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def editorial_value_assessment(item: dict[str, object]) -> dict[str, object]:
    topic = str(item.get("topic") or "")
    topic_type = str(item.get("topic_type") or "")
    base = numeric_score(item.get("window_score") or item.get("total_score") or item.get("score"), 0.0)
    source_count = int(item.get("source_count") or len(item.get("sources") or []) or 0)
    appearance = int(item.get("appearance_count") or 0)
    reasons: list[str] = []
    score = base

    if source_count >= 3:
        score += 0.7
        reasons.append("多源交叉，可信度更高")
    elif source_count <= 1:
        score -= 0.15
        reasons.append("单一来源，发布前需要核对")

    if appearance >= 3:
        score += 0.7
        reasons.append("窗口内反复出现，适合做持续跟进")
    elif appearance >= 2:
        score += 0.35
        reasons.append("不止一次出现，有继续发酵迹象")

    if any(token in topic_type for token in ("low_value",)):
        score -= 2.5
        reasons.append("类型偏低价值，应降噪")
    if topic_type in {"sports_result", "sports_controversy", "esports_result", "esports_controversy", "ai_product", "ai_controversy", "entertainment_controversy", "github_automation", "github_ai"}:
        score += 0.55
        reasons.append("题材有明确主线，可转成内容")
    if "国内相关度高" in " ".join(str(v) for v in item.get("why_hot") or []):
        score += 0.45
        reasons.append("国内相关度高，适合中文受众")
    if str(item.get("source_quality_tier") or "") == "low":
        score -= 1.0
        reasons.append("来源质量偏低")

    score = round(max(0.0, min(10.0, score)), 2)
    if score >= 8.3:
        level = "强选题"
    elif score >= 7.2:
        level = "可跟进"
    elif score >= 6.2:
        level = "观察"
    else:
        level = "降噪"

    if not reasons:
        reasons.append("按热度、来源和题材匹配度综合保留")
    return {
        "method": "rule_two_stage",
        "score": score,
        "level": level,
        "reasons": reasons[:4],
    }


def why_it_matters_text(item: dict[str, object]) -> str:
    topic = str(item.get("topic") or "")
    topic_type = str(item.get("topic_type") or "")
    entities = [str(v) for v in item.get("entity_tags") or [] if v]
    entity_text = "、".join(entities[:2])
    if topic == "sports":
        if "result" in topic_type:
            return f"{entity_text or '这场比赛'}已经给后续排名、晋级线或赛程制造新变化，适合做复盘和走势判断。"
        if "controversy" in topic_type:
            return "争议会持续带动评论区讨论，后续官方回应和处罚比单条新闻更重要。"
        return "体育内容的价值不在搬标题，而在抓球队、球员和下一场走势。"
    if topic == "esports":
        return "电竞热点通常会影响版本理解、选手评价和俱乐部舆论，适合拆成复盘或社区争议。"
    if topic == "ai":
        return "AI热点需要判断是否真正影响产品、价格、工作流或创作者效率，避免被行业PR占位。"
    if topic == "entertainment":
        return "娱乐热点的核心是人物、作品和评论区情绪，能否延展取决于冲突是否继续发酵。"
    if topic == "github":
        repo = str(item.get("repo") or item.get("title") or "这个项目")
        return f"{repo} 的价值在于能否真实解决开发或自动化问题，而不是单看 star 数。"
    return "平台热点适合作为传播信号，必须结合原始来源和评论区再判断能不能做内容。"


def watch_next_text(item: dict[str, object]) -> str:
    topic = str(item.get("topic") or "")
    if topic == "sports":
        return "下一步看官方赛后信息、伤停名单、下一场对阵和国内媒体/球迷评论区。"
    if topic == "esports":
        return "下一步看俱乐部公告、选手直播/采访、赛程变化和社区复盘。"
    if topic == "ai":
        return "下一步看官方公告、价格/开放范围、用户实测、竞品反应和开发者反馈。"
    if topic == "entertainment":
        return "下一步看当事人回应、热搜持续时间、票房/口碑和平台评论区情绪。"
    if topic == "github":
        return "下一步看 README、release、issue、demo、star 增速和是否有真实使用案例。"
    return "下一步看原帖扩散、二次引用、评论区分歧和是否有权威来源补充。"


def controversy_point_text(item: dict[str, object]) -> str:
    topic_type = str(item.get("topic_type") or "")
    topic = str(item.get("topic") or "")
    if "controversy" in topic_type or "争议" in " ".join(str(v) for v in item.get("storyline_tags") or []):
        return "争议点已经出现，先核对多方来源，再拆不同立场，不要只搬单边说法。"
    if topic in {"sports", "esports"}:
        return "暂未形成明确争议，优先看评论区对关键人物、裁判、BP或战术的分歧。"
    if topic == "ai":
        return "暂未形成明确争议，重点观察价格、数据安全、版权、效果翻车或开发者反弹。"
    if topic == "entertainment":
        return "暂未形成明确争议，重点看评论区是否围绕人物、作品口碑或商业合作分化。"
    if topic == "github":
        return "暂未形成明确争议，重点看 issue 里是否出现稳定性、授权和维护争议。"
    return "暂未形成明确争议，先看二次传播里的反对意见和补充事实。"


def publication_briefing(item: dict[str, object]) -> dict[str, str]:
    briefing = {
        "what_happened": editorial_summary(item),
        "why_it_matters": why_it_matters_text(item),
        "what_to_watch_next": watch_next_text(item),
        "controversy_point": controversy_point_text(item),
    }
    llm = item.get("llm_editorial") if isinstance(item.get("llm_editorial"), dict) else {}
    if llm:
        mapping = {
            "what_happened": "what_happened",
            "why_it_matters": "why_it_matters",
            "what_to_watch_next": "what_to_watch_next",
            "controversy_point": "controversy_point",
        }
        for target, source_key in mapping.items():
            value = str(llm.get(source_key) or "").strip()
            if value:
                briefing[target] = value[:220]
    return briefing


def apply_llm_editorial_patch(item: dict[str, object], patch: dict[str, object], model: str = "") -> dict[str, object]:
    clean_patch = {
        "model": model or patch.get("model") or "",
        "version": LLM_EDITORIAL_VERSION,
        "editorial_summary": str(patch.get("editorial_summary") or "").strip()[:220],
        "creator_angle": str(patch.get("creator_angle") or "").strip()[:220],
        "why_it_matters": str(patch.get("why_it_matters") or "").strip()[:220],
        "what_to_watch_next": str(patch.get("what_to_watch_next") or "").strip()[:220],
        "controversy_point": str(patch.get("controversy_point") or "").strip()[:220],
        "editorial_value_reason": str(patch.get("editorial_value_reason") or "").strip()[:220],
        "editorial_value_level": str(patch.get("editorial_value_level") or "").strip(),
        "seo_keywords": [str(v).strip() for v in patch.get("seo_keywords") or [] if str(v).strip()][:8],
    }
    score = numeric_score(patch.get("editorial_value_score"), 0.0)
    if score:
        clean_patch["editorial_value_score"] = round(max(0.0, min(10.0, score)), 2)
    item["llm_editorial"] = clean_patch
    return item


def apply_llm_editorial_overrides(item: dict[str, object], review: dict[str, object]) -> None:
    llm = item.get("llm_editorial") if isinstance(item.get("llm_editorial"), dict) else {}
    if not llm:
        return
    if llm.get("editorial_summary"):
        item["editorial_summary"] = str(llm["editorial_summary"])
    if llm.get("creator_angle"):
        item["creator_angle"] = str(llm["creator_angle"])
    if llm.get("editorial_value_score"):
        item["editorial_value_score"] = numeric_score(llm.get("editorial_value_score"), numeric_score(item.get("editorial_value_score")))
    if llm.get("editorial_value_level"):
        item["editorial_value_level"] = str(llm["editorial_value_level"])
    if llm.get("editorial_value_reason"):
        item["editorial_value_reason"] = str(llm["editorial_value_reason"])
    briefing = publication_briefing(item)
    item["publication_briefing"] = briefing
    if llm.get("seo_keywords"):
        item["seo_keywords"] = llm.get("seo_keywords")
    review["method"] = "llm_plus_rule"
    item["editorial_review"] = review


def item_trend_label(item: dict[str, object], reference_time: datetime | None = None) -> str:
    appearance = int(item.get("appearance_count") or 0)
    source_count = int(item.get("source_count") or len(item.get("sources") or []) or 0)
    window_days = int(item.get("window_days") or 0)
    why_text = " ".join(str(v) for v in item.get("why_hot") or [])
    latest = parse_ranked_timestamp(item.get("last_seen_at") or item.get("latest_published_at") or item.get("published_at"))
    if latest and reference_time:
        latest = as_reference_timezone(latest, reference_time)
        age_hours = (reference_time - latest).total_seconds() / 3600
    else:
        age_hours = None

    if window_days >= 7 and appearance >= 3:
        return "一周主线"
    if appearance >= 3:
        return "反复出现"
    if source_count >= 3:
        return "多源交叉"
    if "国内相关度高" in why_text:
        return "国内优先"
    if "12小时" in why_text:
        return "突然升温"
    if "24小时" in why_text:
        return "今日可跟"
    if age_hours is not None and age_hours <= 6:
        return "突然升温"
    if age_hours is not None and age_hours <= 24:
        return "今日可跟"
    return "待观察"


def semantic_event_key(item: dict[str, object], fallback_title: str | None = None) -> str:
    topic = str(item.get("topic") or "")
    if item.get("event_key") and topic == "entertainment":
        return f"{topic}:{item['event_key']}"
    entity_tags = [str(v) for v in item.get("entity_tags") or [] if v]
    league_tags = [str(v) for v in item.get("league_tags") or [] if v]
    storyline_tags = [str(v) for v in item.get("storyline_tags") or [] if v]
    keyword_hits = [str(v) for v in item.get("keyword_hits") or [] if v]
    title = str(fallback_title or item.get("title") or "")
    if topic in {"sports", "esports"}:
        strong_entities = entity_tags[:3] or league_tags[:2]
        if len(strong_entities) >= 2 or re.search(r"\bvs\b|VS|对阵|\d+\s*[-:比]\s*\d+", title):
            parts = strong_entities[:3] + storyline_tags[:1] + keyword_hits[:1]
            if parts:
                return f"{topic}:" + "|".join(parts)
    if topic == "github" and item.get("repo"):
        return f"github:{item['repo']}"
    if topic == "ai":
        entities = [v for v in entity_tags[:2] if v]
        if entities and keyword_hits:
            return f"ai:{'|'.join(entities + keyword_hits[:1])}"
    return ""


def enrich_item_for_publication(item: dict[str, object]) -> dict[str, object]:
    attach_detail_metadata(item)
    item["editorial_summary"] = editorial_summary(item)
    item["content_angles"] = content_angles(item)
    item["discussion_focus"] = discussion_focus(item)
    review = editorial_value_assessment(item)
    item["editorial_review"] = review
    item["editorial_value_score"] = review["score"]
    item["editorial_value_level"] = review["level"]
    item["editorial_value_reason"] = "；".join(str(v) for v in review.get("reasons") or [])
    item["publication_briefing"] = publication_briefing(item)
    topic_label = str(item.get("topic_label") or item.get("topic") or "热点")
    item["creator_angle"] = brief_creator_angle(item, topic_label)
    apply_llm_editorial_overrides(item, review)
    item["trend_label"] = item_trend_label(item)
    if not item.get("event_key"):
        key = semantic_event_key(item)
        if key:
            item["event_key"] = key
    source_count = int(item.get("source_count") or 0)
    if source_count > 1:
        item["source_signal"] = f"{source_count} 个来源交叉出现"
    else:
        item["source_signal"] = "单一来源，建议打开原文核对"
    return item


def enrich_items_for_publication(items: list[dict[str, object]]) -> list[dict[str, object]]:
    for item in items:
        if isinstance(item, dict):
            enrich_item_for_publication(item)
    return items


def llm_editor_enabled() -> bool:
    flag = os.environ.get("HOTSPOT_LLM_EDITOR_ENABLED", "auto").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    return bool(os.environ.get("HOTSPOT_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def openai_api_key() -> str:
    return os.environ.get("HOTSPOT_OPENAI_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()


def llm_live_enabled() -> bool:
    flag = os.environ.get("HOTSPOT_LLM_LIVE_ENABLED", "1").strip().lower()
    return flag not in {"0", "false", "off", "no", "cache", "cache_only", "cache-only"}


def format_openai_error_response(response: requests.Response) -> str:
    status = response.status_code
    try:
        payload = response.json()
    except Exception:
        text = response.text.strip().replace("\n", " ")
        return f"OpenAI API HTTP {status}: {text[:180]}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        error_type = str(error.get("type") or "").strip()
        parts = [f"OpenAI API HTTP {status}"]
        if code:
            parts.append(f"code={code}")
        if error_type:
            parts.append(f"type={error_type}")
        if message:
            parts.append(message)
        return " | ".join(parts)[:320]
    return f"OpenAI API HTTP {status}: {json.dumps(payload, ensure_ascii=False)[:220]}"


def llm_error_is_known_non_core(error: object) -> bool:
    text = str(error or "")
    return any(code in text for code in KNOWN_LLM_NON_CORE_ERROR_CODES)


def load_llm_editorial_cache() -> dict[str, object]:
    if not LLM_EDITORIAL_CACHE_PATH.exists():
        return {"version": LLM_EDITORIAL_VERSION, "items": {}}
    try:
        payload = json.loads(LLM_EDITORIAL_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": LLM_EDITORIAL_VERSION, "items": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
        return {"version": LLM_EDITORIAL_VERSION, "items": {}}
    return payload


def save_llm_editorial_cache(cache: dict[str, object]) -> None:
    LLM_EDITORIAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache["version"] = LLM_EDITORIAL_VERSION
    cache["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(LLM_EDITORIAL_CACHE_PATH, cache)


def llm_item_cache_key(item: dict[str, object], model: str) -> str:
    fields = {
        "version": LLM_EDITORIAL_VERSION,
        "model": model,
        "topic": item.get("topic"),
        "source_topic": item.get("source_topic"),
        "title": item.get("title"),
        "summary": item_summary(item),
        "source": item.get("source"),
        "type": item.get("topic_type"),
        "score": item.get("window_score") or item.get("total_score") or item.get("score"),
        "event_key": item.get("event_key"),
    }
    raw = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_llm_editorial_candidates(items: list[dict[str, object]]) -> list[dict[str, object]]:
    try:
        per_topic = max(1, int(os.environ.get("HOTSPOT_LLM_TOP_PER_TOPIC", "8")))
    except ValueError:
        per_topic = 5
    try:
        max_items = max(1, int(os.environ.get("HOTSPOT_LLM_MAX_ITEMS", "60")))
    except ValueError:
        max_items = 30
    grouped: dict[str, list[dict[str, object]]] = {topic: [] for topic in ALL_TOPICS}
    for item in items:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "sports")
        grouped.setdefault(topic, []).append(item)
    selected: list[dict[str, object]] = []
    for topic in ALL_TOPICS:
        rows = sorted(
            grouped.get(topic, []),
            key=lambda row: -numeric_score(row.get("editorial_value_score") or row.get("window_score") or row.get("total_score") or row.get("score")),
        )
        selected.extend(rows[:per_topic])
    return selected[:max_items]


def llm_prompt_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for item in items:
        rows.append(
            {
                "id": str(item.get("hotspot_id") or stable_item_id(item)),
                "topic": item.get("topic"),
                "source_topic": item.get("source_topic") or item.get("platform_source") or "",
                "topic_type": item.get("topic_type"),
                "title": item.get("title"),
                "summary": item_summary(item)[:220],
                "source": item.get("source"),
                "score": item.get("editorial_value_score") or item.get("window_score") or item.get("total_score") or item.get("score"),
                "trend_label": item.get("trend_label") or item_trend_label(item),
                "why_hot": [str(v) for v in item.get("why_hot") or [] if v][:5],
                "tags": [str(v) for v in (item.get("entity_tags") or []) + (item.get("keyword_hits") or []) + (item.get("storyline_tags") or []) if v][:10],
            }
        )
    return rows


def build_llm_editorial_prompt(items: list[dict[str, object]]) -> str:
    payload = llm_prompt_items(items)
    return (
        "你是中文自媒体热点编辑总监。请只输出 JSON，不要解释。\n"
        "目标：把热点改成真正给创作者用的摘要、选题切口、后续观察和SEO关键词。\n"
        "要求：中文；具体；不要写泛话术；不要写“24小时内发酵/12小时内更新”；不要夸大事实；博彩广告不要写入新闻判断。\n"
        "每个输入返回一个对象，字段：id, editorial_summary, creator_angle, why_it_matters, what_to_watch_next, controversy_point, "
        "editorial_value_score, editorial_value_level, editorial_value_reason, seo_keywords。\n"
        "editorial_value_level 只能是 强选题 / 可跟进 / 观察 / 降噪。score 0-10。\n"
        "creator_angle 必须是一句话可直接用于选题，不要超过80字。\n"
        "输入：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def extract_openai_response_text(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    chunks: list[str] = []
    for entry in payload.get("output") or []:
        if not isinstance(entry, dict):
            continue
        for content in entry.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks).strip()
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
    return ""


def parse_llm_editorial_response(text: str) -> list[dict[str, object]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\[[\s\S]+\])", cleaned)
        if not match:
            return []
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("results") or []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def call_llm_editorial(items: list[dict[str, object]], model: str) -> list[dict[str, object]]:
    key = openai_api_key()
    if not key or not items:
        return []
    try:
        timeout = max(20, int(os.environ.get("HOTSPOT_LLM_TIMEOUT", "90")))
    except ValueError:
        timeout = 90
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": build_llm_editorial_prompt(items),
            "max_output_tokens": 5000,
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(format_openai_error_response(response))
    text = extract_openai_response_text(response.json())
    return parse_llm_editorial_response(text)


def apply_llm_editorial_to_items(items: list[dict[str, object]], reference_time: datetime) -> dict[str, object]:
    if not llm_editor_enabled():
        return {"enabled": False, "reason": "missing_or_disabled_openai_api_key", "applied": 0}
    model = DEFAULT_LLM_MODEL
    cache = load_llm_editorial_cache()
    cache_items = cache.setdefault("items", {})
    if not isinstance(cache_items, dict):
        cache_items = {}
        cache["items"] = cache_items

    candidates = select_llm_editorial_candidates(items)
    id_to_item = {str(item.get("hotspot_id") or stable_item_id(item)): item for item in candidates}
    pending: list[dict[str, object]] = []
    applied = 0
    for item in candidates:
        cache_key = llm_item_cache_key(item, model)
        item["_llm_cache_key"] = cache_key
        cached = cache_items.get(cache_key)
        if isinstance(cached, dict):
            apply_llm_editorial_patch(item, cached, model=model)
            enrich_item_for_publication(item)
            applied += 1
        else:
            pending.append(item)

    errors: list[str] = []
    requested_count = len(pending)
    live_enabled = llm_live_enabled()
    if pending and not live_enabled:
        for item in candidates:
            item.pop("_llm_cache_key", None)
        return {
            "enabled": True,
            "live_enabled": False,
            "model": model,
            "version": LLM_EDITORIAL_VERSION,
            "candidate_count": len(candidates),
            "applied": applied,
            "requested": 0,
            "remaining": max(0, len(candidates) - applied),
            "errors": [],
            "degraded_reason": "llm_live_disabled_cache_only",
            "generated_at": reference_time.isoformat(),
        }
    try:
        chunk_size = max(1, int(os.environ.get("HOTSPOT_LLM_CHUNK_SIZE", "8")))
    except ValueError:
        chunk_size = 8
    fatal_degraded_reason = ""
    for start in range(0, len(pending), chunk_size):
        chunk = pending[start : start + chunk_size]
        try:
            rows = call_llm_editorial(chunk, model)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)[:320]
            errors.append(message)
            if llm_error_is_known_non_core(message):
                fatal_degraded_reason = "openai_unsupported_country_region_territory"
                break
            continue
        for row in rows:
            item_id = str(row.get("id") or "")
            item = id_to_item.get(item_id)
            if item is None:
                continue
            apply_llm_editorial_patch(item, row, model=model)
            enrich_item_for_publication(item)
            cache_key = str(item.get("_llm_cache_key") or llm_item_cache_key(item, model))
            cache_items[cache_key] = item.get("llm_editorial")
            applied += 1
    for item in candidates:
        item.pop("_llm_cache_key", None)
    if applied or pending:
        save_llm_editorial_cache(cache)
    return {
        "enabled": True,
        "live_enabled": live_enabled,
        "model": model,
        "version": LLM_EDITORIAL_VERSION,
        "candidate_count": len(candidates),
        "applied": applied,
        "requested": requested_count,
        "remaining": max(0, len(candidates) - applied),
        "errors": errors[:5],
        "degraded_reason": fatal_degraded_reason,
        "generated_at": reference_time.isoformat(),
    }


def public_title_similarity(a: object, b: object) -> float:
    left = re.sub(r"[^\w\u4e00-\u9fff]+", "", clean_public_title(str(a or "")).lower())
    right = re.sub(r"[^\w\u4e00-\u9fff]+", "", clean_public_title(str(b or "")).lower())
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left[:90], right[:90]).ratio()


def semantic_merge_key(item: dict[str, object]) -> str:
    topic = str(item.get("topic") or "")
    key = str(item.get("event_key") or semantic_event_key(item) or "").strip()
    if key:
        return key
    if topic == "github" and item.get("repo"):
        return f"github:{item['repo']}"
    return ""


def merge_publication_item(existing: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    def values_list(value: object) -> list[object]:
        if isinstance(value, list):
            return value
        if value:
            return [value]
        return []

    existing_score = numeric_score(existing.get("window_score") or existing.get("total_score") or existing.get("score"))
    current_score = numeric_score(current.get("window_score") or current.get("total_score") or current.get("score"))
    base, other = (current, existing) if current_score > existing_score else (existing, current)
    merged = dict(base)
    merged["sources"] = merge_source_rows(base.get("sources"), other.get("sources"))
    merged["source_count"] = len(merged.get("sources") or []) or max(int(base.get("source_count") or 0), int(other.get("source_count") or 0))
    for field in ("why_hot", "storyline_tags", "keyword_hits", "league_tags", "entity_tags", "content_angles", "discussion_focus", "seo_keywords"):
        merged[field] = list(dict.fromkeys([str(v) for v in values_list(base.get(field)) + values_list(other.get(field)) if v]))[:8]
    if base.get("llm_editorial") or other.get("llm_editorial"):
        merged["llm_editorial"] = base.get("llm_editorial") or other.get("llm_editorial")
    for field in ("appearance_count",):
        merged[field] = max(int(base.get(field) or 0), int(other.get(field) or 0))
    for field in ("first_seen_at", "published_at"):
        values = [str(v) for v in (base.get(field), other.get(field)) if v]
        if values:
            merged[field] = min(values)
    for field in ("last_seen_at", "latest_published_at"):
        values = [str(v) for v in (base.get(field), other.get(field)) if v]
        if values:
            merged[field] = max(values)
    history = list(base.get("history_dates") or []) + list(other.get("history_dates") or [])
    if history:
        merged["history_dates"] = list(dict.fromkeys(str(v) for v in history if v))[:8]
    if not merged.get("event_key"):
        key = semantic_merge_key(merged)
        if key:
            merged["event_key"] = key
    enrich_item_for_publication(merged)
    return merged


def semantic_merge_ranked_items(items: list[dict[str, object]], reference_time: datetime, top: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {topic: [] for topic in ALL_TOPICS}
    thresholds = {"sports": 0.86, "esports": 0.86, "ai": 0.84, "entertainment": 0.86, "platform": 0.88, "github": 0.92}

    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = enrich_item_for_publication(raw)
        topic = str(item.get("topic") or "sports")
        key = semantic_merge_key(item)
        matched_idx: int | None = None
        for idx, prev in enumerate(grouped.setdefault(topic, [])):
            prev_key = semantic_merge_key(prev)
            if key and prev_key and key == prev_key:
                matched_idx = idx
                break
            if public_title_similarity(prev.get("title"), item.get("title")) >= thresholds.get(topic, 0.88):
                matched_idx = idx
                break
        if matched_idx is None:
            grouped.setdefault(topic, []).append(item)
        else:
            grouped[topic][matched_idx] = merge_publication_item(grouped[topic][matched_idx], item)

    merged_items: list[dict[str, object]] = []
    for topic in ALL_TOPICS:
        topic_items = grouped.get(topic, [])
        topic_items.sort(
            key=lambda row: (
                row.get("pin_rank") is None,
                row.get("pin_rank", 9999),
                -numeric_score(row.get("window_score") or row.get("total_score") or row.get("score")),
                str(row.get("last_seen_at") or row.get("latest_published_at") or ""),
            )
        )
        for item in topic_items[:top]:
            item["trend_label"] = item_trend_label(item, reference_time)
            enrich_item_for_publication(item)
            merged_items.append(item)
    return merged_items


def daily_section_match(item: dict[str, object], spec: dict[str, str]) -> bool:
    if str(item.get("topic") or "") != spec.get("topic"):
        return False
    source_topic = spec.get("source_topic")
    if not source_topic:
        return True
    actual = str(item.get("source_topic") or item.get("platform_source") or "").lower()
    return actual == source_topic


def brief_summary_text(item: dict[str, object], section_label: str) -> str:
    summary = str(item.get("editorial_summary") or item_summary(item) or "").strip()
    generic_tokens = (
        "普通赛果价值一般",
        "先看标题爆点",
        "这条热点具备继续观察价值",
        "只作话题素材",
        "金牌搬运工",
        "Score-电竞玩家赛事社区",
        "行业稿偏多",
        "视频选题先抓核心段落",
        "X 传播极快",
    )
    if summary and not any(token in summary for token in generic_tokens):
        return summary
    topic = str(item.get("topic") or "")
    topic_type = str(item.get("topic_type") or "")
    if topic == "sports":
        if "result" in topic_type:
            return "赛果已经形成明确主线，适合做赛后复盘、关键人物和后续走势跟进。"
        if "preview" in topic_type:
            return "赛前关注度较高，适合围绕阵容、伤停、对阵悬念做预热。"
        return "体育话题正在发酵，适合结合赛程、球员和评论区找内容切口。"
    if topic == "esports":
        return "电竞讨论集中在赛事、选手或俱乐部动作，适合做复盘、转会和社区争议切口。"
    if topic == "github":
        return "开发者热度上升，适合核对 README、star 增长和真实使用场景。"
    if topic == "ai":
        return "AI 话题具备产品或行业讨论价值，适合跟进功能、价格、开放范围和实测反馈。"
    if topic == "platform":
        return f"{section_label} 上的讨论正在扩散，适合提炼观点、评论区情绪和二次传播素材。"
    return "热点正在发酵，适合结合来源、评论区和后续进展再做选题。"


def title_has(title: str, words: tuple[str, ...] | list[str]) -> bool:
    lowered = title.lower()
    return any(str(word).lower() in lowered for word in words)


def brief_creator_angle(item: dict[str, object], section_label: str) -> str:
    title = str(item.get("title") or "")
    topic = str(item.get("topic") or "")
    topic_type = str(item.get("topic_type") or "")
    repo = str(item.get("repo") or title).strip()

    if topic == "sports":
        if title_has(title, ("蓉城", "费利佩", "七连胜", "绝杀")):
            return "切口：蓉城七连胜和费利佩绝杀，适合做赛后复盘、强队状态和下一轮走势。"
        if title_has(title, ("阿森纳", "马竞", "欧冠")) and title_has(title, ("决赛", "出局", "晋级")):
            return "切口：阿森纳进决赛和马竞出局，适合做豪门命运、关键进球和决赛前瞻。"
        if title_has(title, ("伤退", "复出", "缺阵", "出战成疑")):
            return "切口：伤病对战术和后续赛程的影响，比单纯报赛果更适合跟进。"
        if "result" in topic_type or title_has(title, ("绝杀", "逆转", "晋级", "淘汰", "破门")):
            return "切口：抓比分转折、关键球员和下一场对阵，做一条赛后复盘主线。"
        return "切口：先找球队、球员和赛程变化，再决定做复盘、人物还是前瞻。"

    if topic == "esports":
        if title_has(title, ("收购", "阵容", "转会", "续约", "重返")):
            return "切口：战队阵容和资本动作会影响赛区格局，适合做转会窗和俱乐部跟进。"
        if title_has(title, ("Gumayusi", "HLE", "结婚")):
            return "切口：明星选手个人选择叠加夺冠目标，适合做人设、粉丝情绪和赛区讨论。"
        if title_has(title, ("处罚", "争议", "道歉", "禁赛")):
            return "切口：争议内容先看俱乐部回应和粉丝分歧，别只搬标题。"
        return "切口：围绕选手、战队、版本和赛果拆，优先找社区真正会吵的点。"

    if topic == "github":
        clean_repo = repo.split("｜", 1)[0].strip()
        return f"切口：用一句话讲清 {clean_repo} 解决什么问题，再看 star、demo、README 和能不能做工具教程。"

    if topic == "ai":
        if title_has(title, ("DeepSeek", "国产算力", "成本")):
            return "切口：模型发布和国产算力成本战，适合做谁受益、谁被压价、创作者能不能用。"
        if title_has(title, ("马斯克", "OpenAI", "诉讼", "火星")):
            return "切口：OpenAI 权力斗争和商业化路线，适合做人物冲突、资本和安全边界。"
        if title_has(title, ("智能体", "Agent", "agent")):
            return "切口：别只讲概念，重点看智能体能替人做什么、成本多少、谁已经落地。"
        return "切口：优先拆产品变化、真实使用场景和对普通创作者的影响。"

    if topic == "platform":
        source_topic = str(item.get("source_topic") or "").lower()
        if source_topic == "x":
            if title_has(title, ("网络攻击", "AI被恶用", "安全", "风险")):
                return "切口：AI 安全风险适合做观点型内容，重点放在真实案例和防护机制。"
            if title_has(title, ("GovTech", "公共治理", "哈萨克斯坦")):
                return "切口：AI 公共治理案例，适合做“国外怎么用 AI 改政府服务”的观察。"
            return "切口：只提炼核心观点和评论区分歧，不要把 X 原帖整段搬运。"
        if source_topic == "youtube":
            if title_has(title, ("GPT", "ChatGPT", "OpenAI", "记忆")):
                return "切口：把视频拆成产品更新、记忆功能影响和普通用户实际变化。"
            if title_has(title, ("Claude", "OpenClaw", "工作流")):
                return "切口：工具封禁和工作流重构，适合做踩坑记录、替代方案和效率教程。"
            return "切口：先定位视频里最有信息量的一段，再拆成短内容或教程。"
        return f"切口：{section_label} 热点只做观点提炼和二次传播，不要直接搬平台标题。"

    if topic == "entertainment":
        return "切口：先判断是人物、作品还是争议，再看评论区情绪能不能延展。"

    return "切口：先核对来源，再找能持续跟进的人物、冲突和后续变化。"


def brief_item_payload(item: dict[str, object], rank: int, section_key: str, section_label: str) -> dict[str, object]:
    detail_url = str(item.get("detail_url") or item_detail_url(item) or "").strip()
    original_url = str(item_public_url(item) or "").strip()
    score = item.get("total_score", item.get("score"))
    try:
        score_value: float | str | None = round(float(score), 2)
    except (TypeError, ValueError):
        score_value = score if score not in (None, "") else None
    return {
        "rank": rank,
        "section": section_key,
        "section_label": section_label,
        "title": str(item.get("title") or ""),
        "category": section_label,
        "topic": item.get("topic"),
        "source_topic": item.get("source_topic") or item.get("platform_source") or item.get("topic"),
        "source": item.get("source") or "",
        "source_domain": item.get("source_domain") or item_source_domain(item),
        "score": score_value,
        "url": detail_url or original_url,
        "detail_url": detail_url,
        "original_url": original_url,
        "summary": brief_summary_text(item, section_label),
        "creator_angle": item.get("creator_angle") or brief_creator_angle(item, section_label),
        "trend_label": item.get("trend_label") or item_trend_label(item),
        "editorial_value_score": item.get("editorial_value_score"),
        "editorial_value_level": item.get("editorial_value_level") or "",
        "editorial_value_reason": item.get("editorial_value_reason") or "",
        "publication_briefing": item.get("publication_briefing") or {},
        "summary_hint": item.get("summary_hint") or "",
        "why_hot": [str(value) for value in item.get("why_hot") or [] if value][:4],
        "content_angles": [str(value) for value in item.get("content_angles") or [] if value][:4],
        "discussion_focus": [str(value) for value in item.get("discussion_focus") or [] if value][:8],
        "storyline_tags": item.get("storyline_tags") or [],
        "keyword_hits": item.get("keyword_hits") or [],
        "entity_tags": item.get("entity_tags") or [],
        "published_at": item.get("published_at"),
        "latest_published_at": item.get("latest_published_at") or item.get("published_at"),
        "source_count": item.get("source_count") or len(item.get("sources") or []),
    }


def render_daily_brief_text(payload: dict[str, object]) -> str:
    section_emojis = {
        "sports": "🏟",
        "esports": "🎮",
        "github": "🧩",
        "ai": "🤖",
        "x": "📡",
        "youtube": "▶️",
    }
    lines = [
        f"今日热点｜{payload.get('run_date') or payload.get('date') or ''}".strip(),
        "",
        "今日最热摘要",
        str(payload.get("summary") or ""),
        "",
    ]
    for section in payload.get("sections") or []:
        if not isinstance(section, dict):
            continue
        items = section.get("items") or []
        if not items:
            continue
        key = str(section.get("key") or "")
        label = str(section.get("label") or key)
        emoji = section_emojis.get(key, "•")
        lines.append(f"{emoji} {label}热点（{len(items)}条）")
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            source = str(item.get("source") or "")
            score = item.get("score")
            score_text = f"｜{score}" if score not in (None, "") else ""
            lines.append(f"{item.get('rank')}. {title}（{label}｜{source}{score_text}）")
            summary = str(item.get("summary") or "").strip()
            if summary:
                lines.append(f"   - 摘要：{summary}")
            creator_angle = str(item.get("creator_angle") or "").strip()
            if creator_angle:
                lines.append(f"   - 切口：{creator_angle.removeprefix('切口：')}")
            value_level = str(item.get("editorial_value_level") or "").strip()
            value_reason = str(item.get("editorial_value_reason") or "").strip()
            if value_level:
                reason_text = f"，{value_reason}" if value_reason else ""
                lines.append(f"   - 价值：{value_level}{reason_text}")
            if item.get("url"):
                lines.append(f"   - 详情：{item['url']}")
        lines.append("")
    lines.append(
        "说明：热点来自 sports-hotspot-dashboard；详情页保留原始来源、摘要、选题切口和核对信息。"
        "天气、黄历不由本站生成，由私域每日推送脚本在发送时另行拼接。"
    )
    return "\n".join(lines).strip()


def build_daily_brief_payload(
    ranked_payload: dict[str, object],
    reference_time: datetime,
    per_section: int = 2,
) -> dict[str, object]:
    raw_items = ranked_payload.get("items")
    items = [enrich_item_for_publication(item) for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    sections: list[dict[str, object]] = []
    flat_items: list[dict[str, object]] = []

    for spec in DAILY_BRIEF_SECTIONS:
        selected: list[dict[str, object]] = []
        for item in items:
            if not daily_section_match(item, spec):
                continue
            if low_value_item_title(str(item.get("topic") or ""), str(item.get("title") or "")):
                continue
            selected.append(item)
            if len(selected) >= per_section:
                break
        section_items = [
            brief_item_payload(item, idx, str(spec["key"]), str(spec["label"]))
            for idx, item in enumerate(selected, 1)
        ]
        flat_items.extend(section_items)
        sections.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "count": len(section_items),
                "items": section_items,
            }
        )

    section_summary = "、".join(f"{section['label']} {section['count']}" for section in sections)
    payload = {
        "ok": True,
        "date": ranked_payload.get("date"),
        "run_date": ranked_payload.get("run_date"),
        "reference_time": ranked_payload.get("reference_time") or reference_time.isoformat(),
        "generated_at": reference_time.isoformat(),
        "source": "sports-hotspot-dashboard",
        "site_url": SITE_BASE_URL,
        "per_section": per_section,
        "summary": f"按重要性分区：{section_summary}。",
        "link_policy": "url 默认指向站内详情页；original_url 保留原始来源链接。",
        "weather_almanac_policy": "本站只输出热点正文；天气和黄历由私域每日推送脚本按发送位置和日期拼接。",
        "sections": sections,
        "items": flat_items,
    }
    payload["text"] = render_daily_brief_text(payload)
    return payload


def write_daily_brief_payload(
    output_dir: Path,
    ranked_payload: dict[str, object],
    reference_time: datetime,
    per_section: int = 2,
) -> Path:
    path = output_dir / "latest_daily_brief.json"
    write_json(path, build_daily_brief_payload(ranked_payload, reference_time, per_section=per_section))
    return path


def url_domain(url: object) -> str:
    try:
        return urlparse(str(url or "")).netloc
    except Exception:
        return ""


def item_summary(item: dict[str, object]) -> str:
    return str(
        item.get("summary")
        or item.get("recommend_reason")
        or item.get("editor_note")
        or item.get("summary_hint")
        or ""
    ).strip()


def item_source_domain(item: dict[str, object]) -> str:
    sources = item.get("sources")
    if isinstance(sources, list):
        for row in sources:
            if isinstance(row, dict) and row.get("domain"):
                return str(row.get("domain") or "").strip()
    return url_domain(item_public_url(item))


def meta_description(text_value: object, fallback: object = "", max_chars: int = 155) -> str:
    text = HTML_TAG_RE.sub(" ", str(text_value or ""))
    text = re.sub(r"\s+", " ", text).strip(" ，。；、")
    if not text:
        text = HTML_TAG_RE.sub(" ", str(fallback or ""))
        text = re.sub(r"\s+", " ", text).strip(" ，。；、")
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip(" ，。；、") + "。"
    return text


def normalize_indexnow_key(value: object) -> str:
    key = str(value or "").strip()
    return key if INDEXNOW_KEY_PATTERN.fullmatch(key) else ""


def ensure_indexnow_key_file(site_root: Path) -> str:
    key_path = site_root / INDEXNOW_KEY_FILE
    env_key = normalize_indexnow_key(os.environ.get("HOTSPOT_INDEXNOW_KEY"))
    existing_key = ""
    if key_path.exists():
        try:
            existing_key = normalize_indexnow_key(key_path.read_text(encoding="utf-8"))
        except OSError:
            existing_key = ""
    key = env_key or existing_key or secrets.token_hex(24)
    key_path.write_text(key + "\n", encoding="utf-8")
    return key


def render_json_ld(structured_data: object | None) -> str:
    if not structured_data:
        return ""
    payload = structured_data
    return (
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "</script>"
    )


def organization_jsonld() -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "RDXW 热点雷达",
        "url": SITE_BASE_URL,
        "logo": page_url("og-preview.svg"),
    }


def webpage_jsonld(title: str, description: str, canonical: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "url": canonical,
        "description": description,
        "inLanguage": "zh-CN",
        "isPartOf": {"@type": "WebSite", "name": "RDXW 热点雷达", "url": SITE_BASE_URL},
    }


def breadcrumb_jsonld(items: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": idx, "name": name, "item": url}
            for idx, (name, url) in enumerate(items, 1)
        ],
    }


def static_page_shell(
    title: str,
    description: str,
    canonical: str,
    body: str,
    structured_data: object | None = None,
    robots: str = "index,follow,max-snippet:-1,max-image-preview:large",
) -> str:
    json_ld = ""
    schema_items: list[object] = [organization_jsonld(), webpage_jsonld(title, description, canonical)]
    if isinstance(structured_data, list):
        schema_items.extend(structured_data)
    elif structured_data:
        schema_items.append(structured_data)
    json_ld = render_json_ld(schema_items)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}" />
  <meta name="theme-color" content="#f5f5f7" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-title" content="RDXW 热点雷达" />
  <link rel="canonical" href="{escape(canonical)}" />
  <link rel="icon" href="/og-preview.svg" type="image/svg+xml" />
  <link rel="apple-touch-icon" href="/og-preview.svg" />
  <link rel="manifest" href="/site.webmanifest" />
  <meta name="robots" content="{escape(robots)}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="RDXW 热点雷达" />
  <meta property="og:title" content="{escape(title)}" />
  <meta property="og:description" content="{escape(description)}" />
  <meta property="og:url" content="{escape(canonical)}" />
  <meta property="og:image" content="{escape(page_url('og-preview.svg'))}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escape(title)}" />
  <meta name="twitter:description" content="{escape(description)}" />
  <style>
    :root{{--bg:#f5f5f7;--text:#111114;--muted:#6e6e73;--line:rgba(15,23,42,.1);--panel:rgba(255,255,255,.84);--blue:#0071e3}}
    *{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#fff,var(--bg));color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}}
    a{{color:inherit;text-decoration:none}}.wrap{{width:min(1080px,calc(100vw - 28px));margin:0 auto;padding:28px 0 52px}}
    .nav{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:28px}}.nav a{{padding:9px 13px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.72);color:var(--muted);font-size:13px}}
    .hero{{padding:34px;border-radius:32px;background:var(--panel);border:1px solid rgba(255,255,255,.9);box-shadow:0 24px 70px rgba(15,23,42,.08);margin-bottom:22px}}
    .eyebrow{{margin:0 0 10px;color:var(--muted);font-size:12px;letter-spacing:.12em;text-transform:uppercase}}h1{{margin:0;font-size:clamp(38px,6vw,72px);line-height:1;letter-spacing:-.05em}}.desc{{margin:16px 0 0;color:var(--muted);font-size:16px}}
    .list{{display:grid;gap:14px}}.grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.grid-3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}article{{padding:22px;border-radius:24px;background:var(--panel);border:1px solid rgba(255,255,255,.9);box-shadow:0 12px 34px rgba(15,23,42,.06)}}h2{{margin:0 0 10px;font-size:22px;line-height:1.28;letter-spacing:-.02em}}.meta{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;color:var(--muted);font-size:13px}}.pill{{padding:5px 9px;border:1px solid var(--line);border-radius:999px;background:#fff}}p{{margin:0;color:#333}}.source{{margin-top:12px;color:var(--blue);font-size:14px}}footer{{margin-top:28px;color:var(--muted);font-size:13px}}
    .hero-actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:22px}}.button{{display:inline-flex;align-items:center;justify-content:center;padding:11px 16px;border-radius:999px;background:#111114;color:#fff;font-weight:700;font-size:14px;border:0;cursor:pointer}}.button:disabled{{opacity:.58;cursor:not-allowed}}.button.secondary{{background:#fff;color:#111114;border:1px solid var(--line)}}.kicker{{margin:0 0 8px;color:var(--muted);font-size:13px;font-weight:700}}.rank-list{{list-style:none;margin:0;padding:0;display:grid;gap:10px}}.rank-list li{{display:grid;grid-template-columns:auto 1fr;gap:10px;margin:0;align-items:start}}.rank-num{{width:26px;height:26px;border-radius:999px;background:#eef3ff;color:#0071e3;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:800}}.rank-title{{font-weight:700;line-height:1.42}}.rank-desc{{display:block;color:var(--muted);font-size:13px;margin-top:3px}}.landing-section{{margin-top:18px}}.quote-box{{padding:18px;border-radius:22px;background:#111114;color:#fff}}.quote-box p{{color:#fff}}.feedback-form{{display:grid;gap:14px}}.feedback-form label{{display:grid;gap:6px;color:var(--muted);font-size:13px;font-weight:700}}.feedback-form input,.feedback-form select,.feedback-form textarea{{width:100%;border:1px solid var(--line);border-radius:16px;background:#fff;color:var(--text);padding:12px 14px;font:inherit;outline:none}}.feedback-form textarea{{min-height:160px;resize:vertical}}.hp-field{{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}}.help-text{{color:var(--muted);font-size:13px}}@media(max-width:860px){{.grid-2,.grid-3{{grid-template-columns:1fr}}}}
    .detail-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.detail-grid article:first-child,.detail-grid article:last-child{{grid-column:1/-1}}ul{{margin:0;padding-left:20px;color:#333}}li{{margin:6px 0}}.source-detail-list{{list-style:none;padding:0;display:grid;gap:10px}}.source-detail-list li{{margin:0;padding:12px;border:1px solid var(--line);border-radius:16px;background:#fff}}.source-detail-list span{{display:block;color:var(--muted);font-size:12px}}.source-detail-list p{{margin-top:4px;font-size:14px}}@media(max-width:760px){{.detail-grid{{grid-template-columns:1fr}}}}
    .desktop-sponsor{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 0 18px;padding:16px 18px;border-radius:26px;color:#fff;background:radial-gradient(circle at 8% 0%,rgba(255,255,255,.36),transparent 24%),linear-gradient(120deg,#ff7a18 0%,#ff3b30 48%,#a600ff 100%);border:1px solid rgba(255,255,255,.48);box-shadow:0 18px 46px rgba(255,59,48,.16)}}.desktop-sponsor-copy{{display:flex;align-items:center;gap:14px;min-width:0}}.desktop-sponsor-badge{{flex:0 0 auto;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.2);font-size:12px}}.desktop-sponsor-title{{margin:0;color:#fff;font-size:24px;line-height:1;font-weight:800;letter-spacing:-.04em}}.desktop-sponsor-link{{flex:0 0 auto;padding:10px 15px;border-radius:999px;background:rgba(255,255,255,.92);color:#111114;font-size:13px;font-weight:700;box-shadow:0 10px 24px rgba(15,23,42,.12)}}@media(max-width:900px){{.desktop-sponsor{{display:none}}}}
    .floating-ad{{position:fixed;right:max(14px,env(safe-area-inset-right));bottom:max(16px,env(safe-area-inset-bottom));z-index:80;width:132px;animation:adFloat 5.8s ease-in-out infinite;filter:drop-shadow(0 16px 34px rgba(15,23,42,.18))}}.floating-ad.is-hidden{{display:none}}.floating-ad-link{{position:relative;display:grid;min-height:78px;padding:12px;border-radius:22px;overflow:hidden;color:#fff;background:radial-gradient(circle at 20% 15%,rgba(255,255,255,.34),transparent 26%),linear-gradient(145deg,#ff7a18 0%,#ff3b30 54%,#a600ff 100%);border:1px solid rgba(255,255,255,.45);box-shadow:inset 0 1px 0 rgba(255,255,255,.28)}}.floating-ad-link::after{{content:"";position:absolute;inset:auto -18px -26px auto;width:86px;height:86px;border-radius:50%;background:rgba(255,255,255,.18)}}.floating-ad-tag,.floating-ad-title{{position:relative;z-index:1}}.floating-ad-tag{{width:fit-content;padding:3px 7px;border-radius:999px;background:rgba(255,255,255,.22);font-size:11px;line-height:1}}.floating-ad-title{{align-self:end;font-size:28px;line-height:1;font-weight:800;letter-spacing:-.05em}}.floating-ad-close{{position:absolute;top:-7px;right:-7px;z-index:2;width:24px;height:24px;border:0;border-radius:50%;cursor:pointer;color:rgba(17,17,20,.72);background:rgba(255,255,255,.9);box-shadow:0 8px 18px rgba(15,23,42,.16)}}@keyframes adFloat{{0%,100%{{transform:translate3d(0,0,0) rotate(-1deg)}}50%{{transform:translate3d(0,-10px,0) rotate(1.5deg)}}}}@media(max-width:640px){{.floating-ad{{width:138px;right:max(10px,env(safe-area-inset-right));bottom:max(12px,env(safe-area-inset-bottom))}}.floating-ad-link{{min-height:66px;border-radius:18px;padding:10px}}.floating-ad-title{{font-size:21px;letter-spacing:-.06em}}}}
  </style>
  {json_ld}
</head>
<body>
  <main class="wrap">
    <nav class="nav">
      <a href="/">首页</a><a href="/creator-topics.html">自媒体选题</a><a href="/sports.html">体育</a><a href="/esports.html">电竞</a><a href="/ai.html">AI</a><a href="/topics/index.html">专题</a><a href="/weekly/index.html">周报</a><a href="/methodology.html">方法</a><a href="/api.html">API</a><a href="/feedback.html">反馈</a><a href="/dashboard/index.html">工具</a><a href="/feed.xml">RSS</a>
    </nav>
    <aside class="desktop-sponsor" aria-label="合作推广" data-nosnippet>
      <div class="desktop-sponsor-copy">
        <span class="desktop-sponsor-badge">合作推广</span>
        <p class="desktop-sponsor-title">{escape(SPONSOR_DESKTOP_TEXT)}</p>
      </div>
      <a class="desktop-sponsor-link" href="https://80818.my/" target="_blank" rel="nofollow sponsored noopener noreferrer">立即查看</a>
    </aside>
    {body}
    <footer>
      <span class="byline" data-author="RDXW editor">Editor: RDXW team</span>
      · Updated {escape(dt.datetime.now().strftime("%Y-%m-%d %H:%M"))}
      · Reviewed by RDXW team
      · 自动更新于 {escape(dt.datetime.now().strftime("%Y-%m-%d %H:%M"))}
      · <a href="/about.html">About 关于</a>
      · <a href="/contact.html">Contact 联系</a>
      · <a href="/privacy.html">Privacy 隐私</a>
      · <a href="/terms.html">Terms 条款</a>
      · <a href="/feedback.html">反馈建议</a>
    </footer>
  </main>
  <aside class="floating-ad" id="floatingAd" aria-label="广告" data-nosnippet>
    <button class="floating-ad-close" type="button" aria-label="关闭广告">×</button>
    <a class="floating-ad-link" href="https://80818.my/" target="_blank" rel="nofollow sponsored noopener noreferrer">
      <span class="floating-ad-tag">广告</span>
      <span class="floating-ad-title">{escape(SPONSOR_MOBILE_TEXT)}</span>
    </a>
  </aside>
	  <script>
	    const floatingAd = document.getElementById("floatingAd");
    if (floatingAd) {{
      const key = "rdxw_ad_closed_until";
      const now = Date.now();
      const closedUntil = Number(localStorage.getItem(key) || 0);
      if (closedUntil > now) floatingAd.classList.add("is-hidden");
      floatingAd.querySelector(".floating-ad-close")?.addEventListener("click", () => {{
        localStorage.setItem(key, String(Date.now() + 12 * 60 * 60 * 1000));
        floatingAd.classList.add("is-hidden");
      }});
	    }}
		  </script>
{ANALYTICS_SNIPPET}
</body>
</html>
"""


def topic_item_list_jsonld(items: list[dict[str, object]], page_title: str, canonical: str) -> dict[str, object]:
    elements = []
    for idx, item in enumerate(items, 1):
        url = item_detail_url(item) or canonical
        elements.append(
            {
                "@type": "ListItem",
                "position": idx,
                "url": url,
                "name": str(item.get("title") or ""),
                "description": item_summary(item)[:180],
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": page_title,
        "url": canonical,
        "inLanguage": "zh-CN",
        "mainEntity": {"@type": "ItemList", "itemListElement": elements},
    }


def item_source_count(item: dict[str, object]) -> int:
    for key in ("source_count", "mention_count", "source_mentions"):
        value = item.get(key)
        try:
            parsed = int(float(str(value)))
        except (TypeError, ValueError):
            parsed = 0
        if parsed > 0:
            return parsed
    sources = item.get("sources")
    if isinstance(sources, list):
        count = len([row for row in sources if isinstance(row, dict)])
        if count > 0:
            return count
    signal = str(item.get("source_signal") or "")
    match = re.search(r"(\d+)\s*个来源", signal)
    if match:
        return int(match.group(1))
    return 0


def detail_search_index_decision(item: dict[str, object]) -> tuple[bool, list[str]]:
    if item.get("search_index_candidate") is False:
        return False, ["不在主榜强详情候选，保留站内浏览但不主动提交索引"]
    source_count = item_source_count(item)
    score = numeric_score(item.get("editorial_value_score") or item.get("window_score") or item.get("total_score") or item.get("score"))
    topic = str(item.get("topic") or "")
    value_level = str(item.get("editorial_value_level") or "").strip()
    reasons: list[str] = []
    if source_count >= 3:
        reasons.append(f"{source_count} 个来源交叉")
    if value_level == "强选题" and score >= 9.4 and topic in {"sports", "esports", "ai", "entertainment"}:
        reasons.append(f"强选题且热度 {score:.2f}")
    if topic == "github" and score >= 9.95 and str(item.get("repo") or item.get("title") or "").strip():
        reasons.append(f"GitHub 高热项目 {score:.2f}")
    if reasons:
        return True, reasons
    fallback = "单来源或选题信号不足"
    if value_level:
        fallback += f"：{value_level}"
    if score:
        fallback += f" / 热度 {score:.2f}"
    return False, [fallback]


def detail_is_search_indexable(item: dict[str, object]) -> bool:
    return detail_search_index_decision(item)[0]


def render_hotspot_detail_page(item: dict[str, object]) -> str:
    enrich_item_for_publication(item)
    title_text = str(item.get("title") or "")
    topic_label = str(item.get("topic_label") or item.get("topic") or "热点")
    canonical_path = str(item.get("detail_path") or "")
    canonical = page_url(canonical_path)
    summary = str(item.get("editorial_summary") or item_summary(item) or "")
    external = item_public_url(item)
    latest = str(item.get("last_seen_at") or item.get("latest_published_at") or item.get("published_at") or "")[:16].replace("T", " ")
    score = item.get("window_score") or item.get("total_score") or item.get("score")
    score_text = f"{float(score):.2f}" if isinstance(score, (int, float)) or str(score).replace(".", "", 1).isdigit() else ""
    why_hot = [str(v) for v in item.get("why_hot") or [] if v]
    angles = [str(v) for v in item.get("content_angles") or [] if v]
    focus = [str(v) for v in item.get("discussion_focus") or [] if v]
    briefing = item.get("publication_briefing") if isinstance(item.get("publication_briefing"), dict) else publication_briefing(item)
    value_level = str(item.get("editorial_value_level") or "").strip()
    value_reason = str(item.get("editorial_value_reason") or "").strip()
    sources = [row for row in item.get("sources") or [] if isinstance(row, dict)]

    meta = [
        topic_label,
        str(item.get("topic_type") or ""),
        f"热度 {score_text}" if score_text else "",
        f"选题价值：{value_level}" if value_level else "",
        str(item.get("source_signal") or ""),
        latest,
    ]
    meta_html = "".join(f'<span class="pill">{escape(v)}</span>' for v in meta if v)
    why_html = "".join(f"<li>{escape(v)}</li>" for v in why_hot[:8]) or "<li>暂无明确上榜原因，建议核对来源后再判断。</li>"
    angle_html = "".join(f"<li>{escape(v)}</li>" for v in angles[:6]) or "<li>先看标题爆点，再判断是否值得继续跟进。</li>"
    focus_html = "".join(f'<span class="pill">{escape(v)}</span>' for v in focus)
    related_topic_html = item_related_cluster_links_html(item)
    search_indexable, index_reasons = detail_search_index_decision(item)
    item["search_indexable"] = search_indexable
    item["search_index_reasons"] = index_reasons
    source_html = ""
    if sources:
        rows = []
        for row in sources[:8]:
            label = str(row.get("source") or row.get("name") or "来源")
            row_title = str(row.get("title") or title_text)
            url = str(row.get("url") or "").strip()
            domain_name = str(row.get("domain") or url_domain(url) or "")
            if url:
                rows.append(
                    f'<li><a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(label)}</a>'
                    f'<span>{escape(domain_name)}</span><p>{escape(row_title)}</p></li>'
                )
            else:
                rows.append(f"<li><strong>{escape(label)}</strong><span>{escape(domain_name)}</span><p>{escape(row_title)}</p></li>")
        source_html = "<ul class=\"source-detail-list\">" + "".join(rows) + "</ul>"
    else:
        source_html = "<p>暂无来源列表。</p>"

    source_name = str(item.get("source") or "").strip()
    trend_label = str(item.get("trend_label") or item_trend_label(item)).strip()
    description = meta_description(
        "，".join(
            v
            for v in [
                summary or title_text,
                f"来源：{source_name}" if source_name else "",
                f"频道：{topic_label}",
                f"热度信号：{trend_label}" if trend_label else "",
                "包含事件摘要、上榜依据、讨论焦点和自媒体选题切口",
            ]
            if v
        ),
        fallback=title_text,
    )
    body = f"""<section class="hero">
  <p class="eyebrow">RDXW Hotspot Detail</p>
  <h1>{escape(title_text)}</h1>
  <p class="desc">{escape(description)}</p>
  <div class="meta" style="margin-top:18px">{meta_html}</div>
</section>
<section class="detail-grid">
  <article>
    <h2>发生了什么</h2>
    <p>{escape(str(briefing.get("what_happened") or summary))}</p>
  </article>
  <article>
    <h2>为什么值得看</h2>
    <p>{escape(str(briefing.get("why_it_matters") or ""))}</p>
    {f'<p style="margin-top:10px;color:#555">选题价值：{escape(value_level)}{escape("，" + value_reason if value_reason else "")}</p>' if value_level else ''}
  </article>
  <article>
    <h2>后续看什么</h2>
    <p>{escape(str(briefing.get("what_to_watch_next") or ""))}</p>
  </article>
  <article>
    <h2>争议点</h2>
    <p>{escape(str(briefing.get("controversy_point") or ""))}</p>
  </article>
  <article>
    <h2>自媒体选题切口</h2>
    <ul>{angle_html}</ul>
  </article>
  <article>
    <h2>上榜依据</h2>
    <ul>{why_html}</ul>
  </article>
  <article>
    <h2>讨论焦点</h2>
    <div class="meta">{focus_html or '<span class="pill">待观察</span>'}</div>
  </article>
  {related_topic_html}
  <article>
    <h2>来源与核对</h2>
    {source_html}
    {f'<p class="source"><a href="{escape(external)}" target="_blank" rel="noreferrer">打开原文链接</a></p>' if external else ''}
  </article>
</section>"""
    structured = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title_text,
        "description": description,
        "url": canonical,
        "inLanguage": "zh-CN",
        "keywords": ", ".join(str(v) for v in (item.get("keyword_hits") or item.get("entity_tags") or item.get("discussion_focus") or []) if v),
        "isAccessibleForFree": True,
        "about": [{"@type": "Thing", "name": str(v)} for v in focus[:6]],
        "datePublished": str(item.get("published_at") or item.get("latest_published_at") or ""),
        "dateModified": str(item.get("last_seen_at") or item.get("latest_published_at") or item.get("published_at") or ""),
        "mainEntityOfPage": canonical,
        "publisher": {"@type": "Organization", "name": "RDXW 热点雷达", "url": SITE_BASE_URL},
    }
    structured_payload = [
        structured,
        breadcrumb_jsonld(
            [
                ("首页", page_url("")),
                (topic_label, page_url(topic_page_name(str(item.get("topic") or "sports"), "7d"))),
                (title_text[:60], canonical),
            ]
        ),
    ]
    robots = "index,follow,max-snippet:-1,max-image-preview:large" if search_indexable else "noindex,follow"
    return static_page_shell(f"{title_text} | RDXW 热点详情", description, canonical, body, structured_payload, robots=robots)


def render_topic_static_page(payload: dict[str, object], canonical_path: str) -> str:
    topic_label = str(payload.get("topic_label") or payload.get("topic") or "")
    window_label = str(payload.get("window_label") or "")
    topic_key = str(payload.get("topic") or canonical_path.split("-", 1)[0] or "")
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    title = f"{topic_label} · {window_label} | RDXW 热点雷达"
    description = meta_description(
        f"RDXW 热点雷达整理{topic_label}{window_label}热点，共 {len(items)} 条，覆盖标题摘要、来源核对、热度信号和自媒体选题切口，适合快速筛选可跟进内容。",
        fallback=title,
    )
    canonical = page_url(canonical_path)
    cards = []
    for idx, item in enumerate(items, 1):
        link = item_detail_url(item) or "#"
        external = item_public_url(item)
        summary = item_summary(item)
        creator_angle = str(item.get("creator_angle") or "").removeprefix("切口：").strip()
        trend_label = str(item.get("trend_label") or "").strip()
        value_level = str(item.get("editorial_value_level") or "").strip()
        source = str(item.get("source") or "")
        source_domain = item_source_domain(item)
        latest = str(item.get("last_seen_at") or item.get("latest_published_at") or item.get("published_at") or "")[:16].replace("T", " ")
        meta = [
            f"#{idx}",
            trend_label,
            value_level,
            str(item.get("topic_type") or ""),
            source,
            source_domain,
            latest,
        ]
        meta_html = "".join(f'<span class="pill">{escape(v)}</span>' for v in meta if v)
        source_line = ""
        if source or source_domain:
            source_line = f"来源：{escape(source)} {escape(source_domain)}"
            if external:
                source_line += f' · <a href="{escape(external)}" target="_blank" rel="noreferrer">原文</a>'
        cards.append(
            f"""<article>
  <h2><a href="{escape(link)}" target="_blank" rel="noreferrer">{escape(str(item.get("title") or ""))}</a></h2>
  <div class="meta">{meta_html}</div>
  <p>{escape(summary)}</p>
  {f'<p style="margin-top:8px;color:#555">切口：{escape(creator_angle)}</p>' if creator_angle else ''}
  {f'<div class="source">{source_line}</div>' if source_line else ''}
</article>"""
        )
    related_clusters = related_clusters_for_topic(topic_key, 4)
    related_html = cluster_cards_html(related_clusters)
    body = f"""<section class="hero">
  <p class="eyebrow">RDXW · {escape(window_label)}</p>
  <h1>{escape(topic_label)}</h1>
  <p class="desc">{escape(description)}</p>
</section>
{f'<section class="grid-2 landing-section"><article><h2>本频道重点专题</h2><p>如果只看实时榜容易漏掉持续发酵主线，可以先从这些 7 天专题页进入。</p></article>{related_html}</section>' if related_html else ''}
<section class="list">
  {''.join(cards) if cards else '<article><p>暂无数据</p></article>'}
</section>"""
    structured_payload = [
        topic_item_list_jsonld(items, title, canonical),
        breadcrumb_jsonld([("首页", page_url("")), (topic_label, canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured_payload)


def render_daily_static_page(ranked_payload: dict[str, object]) -> str:
    run_date = str(ranked_payload.get("run_date") or ranked_payload.get("date") or "")
    items = [item for item in ranked_payload.get("items", []) if isinstance(item, dict)]
    title = f"{run_date} 热点日报 | RDXW 热点雷达"
    description = meta_description(
        f"{run_date} RDXW 多频道热点日报，共 {len(items)} 条，覆盖体育、电竞、AI、娱乐、平台热议和 GitHub，提供摘要、来源核对、热度信号和自媒体选题切口。",
        fallback=title,
    )
    canonical_path = f"daily/{run_date}.html"
    canonical = page_url(canonical_path)
    grouped: dict[str, list[dict[str, object]]] = {topic: [] for topic in ALL_TOPICS}
    for item in items:
        grouped.setdefault(str(item.get("topic") or "sports"), []).append(item)
    sections = []
    labels = ranked_payload.get("topic_labels", {})
    for topic in ALL_TOPICS:
        topic_items = grouped.get(topic, [])[:12]
        if not topic_items:
            continue
        cards = []
        for idx, item in enumerate(topic_items, 1):
            link = item_detail_url(item) or "#"
            cards.append(
                f"""<article>
  <h2><a href="{escape(link)}" target="_blank" rel="noreferrer">{escape(str(item.get("title") or ""))}</a></h2>
  <div class="meta"><span class="pill">#{idx}</span><span class="pill">{escape(str(item.get("trend_label") or ""))}</span><span class="pill">{escape(str(item.get("source") or ""))}</span><span class="pill">{escape(item_source_domain(item))}</span></div>
  <p>{escape(item_summary(item))}</p>
</article>"""
            )
        sections.append(f"<h2>{escape(str(labels.get(topic) or topic))}</h2><section class=\"list\">{''.join(cards)}</section>")
    body = f"""<section class="hero">
  <p class="eyebrow">Daily Archive</p>
  <h1>{escape(run_date)} 热点日报</h1>
  <p class="desc">{escape(description)}</p>
</section>
{''.join(sections)}"""
    structured_payload = [
        topic_item_list_jsonld(items[:60], title, canonical),
        breadcrumb_jsonld([("首页", page_url("")), ("热点日报", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured_payload)


def seo_cluster_page_name(slug: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-") or "hot"
    return f"topics/{safe}.html"


def related_clusters_for_topic(topic: str, limit: int = 5) -> list[dict[str, object]]:
    related = [cluster for cluster in SEO_TOPIC_CLUSTERS if topic in {str(v) for v in cluster.get("topics") or []}]
    return related[:limit]


def cluster_intent_keywords(cluster: dict[str, object], limit: int = 6) -> list[str]:
    values = [str(v).strip() for v in cluster.get("intent_keywords") or [] if str(v).strip()]
    if not values:
        label = str(cluster.get("label") or "").strip()
        values = [f"{label}最新", f"{label}今日", f"{label}复盘"] if label else []
    return values[:limit]


def related_clusters_for_cluster(cluster: dict[str, object], limit: int = 4) -> list[dict[str, object]]:
    slug = str(cluster.get("slug") or "")
    topics = {str(v) for v in cluster.get("topics") or []}
    related = [
        row
        for row in SEO_TOPIC_CLUSTERS
        if str(row.get("slug") or "") != slug and topics.intersection({str(v) for v in row.get("topics") or []})
    ]
    if len(related) < limit:
        related.extend(
            row
            for row in SEO_TOPIC_CLUSTERS
            if str(row.get("slug") or "") != slug and row not in related
        )
    return related[:limit]


def related_clusters_for_item(item: dict[str, object], limit: int = 4) -> list[dict[str, object]]:
    direct = [cluster for cluster in SEO_TOPIC_CLUSTERS if cluster_matches_item(cluster, item)]
    if len(direct) < limit:
        topic = str(item.get("topic") or "")
        direct.extend(
            cluster
            for cluster in related_clusters_for_topic(topic, limit)
            if cluster not in direct
        )
    return direct[:limit]


def cluster_keyword_section_html(cluster: dict[str, object]) -> str:
    keywords = cluster_intent_keywords(cluster)
    keyword_html = "".join(f'<span class="pill">{escape(value)}</span>' for value in keywords)
    label = str(cluster.get("label") or "专题")
    return f"""<article>
  <p class="kicker">相关搜索入口</p>
  <h2>{escape(label)}覆盖哪些词</h2>
  <div class="meta">{keyword_html}</div>
  <p>这些词用于承接自然搜索里的长尾查询，用户进来后可以继续看 7 天聚合、实时榜和站内详情页。</p>
</article>"""


def cluster_internal_links_html(cluster: dict[str, object]) -> str:
    links: list[tuple[str, str, str]] = []
    for topic in [str(v) for v in cluster.get("topics") or [] if str(v).strip()]:
        links.append((f"/{topic_page_name(topic, '7d')}", PUBLIC_TOPIC_LABELS.get(topic, topic), "频道 7 天榜"))
    for related in related_clusters_for_cluster(cluster, 4):
        path = seo_cluster_page_name(str(related.get("slug") or "hot"))
        links.append((f"/{path}", str(related.get("label") or "相关专题"), "相关专题"))
    links.append(("/creator-topics.html", "自媒体选题热点日报", "选题入口"))

    seen: set[str] = set()
    rows = []
    for href, label, note in links:
        if href in seen:
            continue
        seen.add(href)
        rows.append(f'<li><a href="{escape(href)}">{escape(label)}</a><span> · {escape(note)}</span></li>')
    return f"""<article>
  <p class="kicker">继续看</p>
  <h2>相关聚合与内链推荐</h2>
  <ul>{''.join(rows)}</ul>
</article>"""


def item_related_cluster_links_html(item: dict[str, object]) -> str:
    clusters = related_clusters_for_item(item, 4)
    if not clusters:
        return ""
    rows = []
    for cluster in clusters:
        path = seo_cluster_page_name(str(cluster.get("slug") or "hot"))
        keywords = "、".join(cluster_intent_keywords(cluster, 3))
        keyword_note = f"<span> · {escape(keywords)}</span>" if keywords else ""
        rows.append(
            f'<li><a href="/{escape(path)}">{escape(str(cluster.get("label") or "相关专题"))}</a>'
            f"{keyword_note}</li>"
        )
    topic = str(item.get("topic") or "")
    topic_label = PUBLIC_TOPIC_LABELS.get(topic, topic)
    if topic:
        rows.append(f'<li><a href="/{escape(topic_page_name(topic, "7d"))}">{escape(topic_label)}</a><span> · 频道 7 天榜</span></li>')
    return f"""<article>
    <h2>继续看相关专题</h2>
    <p>这条热点可以继续进入下面的聚合页，方便从单条新闻回到持续主线。</p>
    <ul>{''.join(rows)}</ul>
  </article>"""


def cluster_cards_html(clusters: list[dict[str, object]], compact: bool = False) -> str:
    cards = []
    for cluster in clusters:
        path = seo_cluster_page_name(str(cluster.get("slug") or "hot"))
        label = str(cluster.get("label") or "")
        description = str(cluster.get("description") or "")
        if compact:
            cards.append(f'<li><a href="/{escape(path)}">{escape(label)}</a><span>7天专题</span></li>')
        else:
            cards.append(
                f"""<article>
  <h2><a href="/{escape(path)}">{escape(label)}</a></h2>
  <div class="meta"><span class="pill">7天专题</span><span class="pill">持续主线</span></div>
  <p>{escape(description)}</p>
</article>"""
            )
    if compact:
        return "<ul>" + "".join(cards) + "</ul>"
    return "".join(cards)


def item_search_blob(item: dict[str, object]) -> str:
    values: list[str] = []
    for key in (
        "title",
        "original_title",
        "summary",
        "editorial_summary",
        "creator_angle",
        "topic_type",
        "source",
        "source_topic",
        "platform_source",
        "repo",
    ):
        value = item.get(key)
        if value:
            values.append(str(value))
    for key in ("entity_tags", "keyword_hits", "storyline_tags", "league_tags", "seo_keywords"):
        values.extend(str(v) for v in item.get(key) or [] if v)
    return " ".join(values).lower()


def cluster_matches_item(cluster: dict[str, object], item: dict[str, object]) -> bool:
    topics = {str(v) for v in cluster.get("topics") or []}
    if topics and str(item.get("topic") or "") not in topics:
        return False
    blob = item_search_blob(item)
    for keyword in cluster.get("keywords") or []:
        token = str(keyword or "").strip().lower()
        if token and token in blob:
            return True
    return False


def collect_cluster_items(ranked_payload: dict[str, object], windows_payload: dict[str, object], cluster: dict[str, object]) -> list[dict[str, object]]:
    pool: list[dict[str, object]] = []
    for raw in ranked_payload.get("items") or []:
        if isinstance(raw, dict):
            pool.append(enrich_item_for_publication(raw))
    seven_day = ((windows_payload.get("windows") or {}).get("7d") or {}).get("items") or []
    for raw in seven_day:
        if isinstance(raw, dict):
            pool.append(enrich_item_for_publication(raw))

    collected: dict[str, dict[str, object]] = {}
    for item in pool:
        if cluster_matches_item(cluster, item):
            key = str(item.get("detail_path") or item.get("hotspot_id") or stable_item_id(item))
            prev = collected.get(key)
            if prev is None or numeric_score(item.get("window_score") or item.get("total_score") or item.get("score")) > numeric_score(prev.get("window_score") or prev.get("total_score") or prev.get("score")):
                collected[key] = item
    items = list(collected.values())
    items.sort(key=lambda row: (-numeric_score(row.get("editorial_value_score") or row.get("window_score") or row.get("total_score") or row.get("score")), str(row.get("last_seen_at") or row.get("latest_published_at") or "")), reverse=False)
    return items[:24]


def render_seo_cluster_page(cluster: dict[str, object], items: list[dict[str, object]], run_date: str) -> str:
    label = str(cluster.get("label") or "")
    base_description = str(cluster.get("description") or f"{label}聚合页")
    description = meta_description(
        f"{base_description} RDXW 按 7 天窗口持续更新，整理相关热点标题、来源、摘要、讨论焦点和自媒体选题切口，适合做专题页、复盘和后续跟进。",
        fallback=f"{label} 7天热点专题聚合",
    )
    slug = str(cluster.get("slug") or normalize_title(label))
    canonical_path = seo_cluster_page_name(slug)
    canonical = page_url(canonical_path)
    title = f"{label} · 7天聚合 | RDXW 热点雷达"
    cards = []
    for idx, item in enumerate(items, 1):
        link = item_detail_url(item) or "#"
        score = item.get("editorial_value_score") or item.get("window_score") or item.get("total_score") or item.get("score")
        score_text = f"{float(score):.2f}" if isinstance(score, (int, float)) or str(score).replace(".", "", 1).isdigit() else ""
        briefing = item.get("publication_briefing") if isinstance(item.get("publication_briefing"), dict) else publication_briefing(item)
        cards.append(
            f"""<article>
  <h2><a href="{escape(link)}">{escape(str(item.get("title") or ""))}</a></h2>
  <div class="meta"><span class="pill">#{idx}</span><span class="pill">{escape(str(item.get("topic_label") or item.get("topic") or ""))}</span><span class="pill">{escape(str(item.get("trend_label") or ""))}</span><span class="pill">选题价值 {escape(str(item.get("editorial_value_level") or ""))}</span>{f'<span class="pill">热度 {escape(score_text)}</span>' if score_text else ''}</div>
  <p>{escape(str(briefing.get("what_happened") or item_summary(item)))}</p>
  <p style="margin-top:8px;color:#555">为什么值得看：{escape(str(briefing.get("why_it_matters") or why_it_matters_text(item)))}</p>
  {f'<p class="source">来源：{escape(str(item.get("source") or ""))} {escape(item_source_domain(item))}</p>' if item.get("source") or item_source_domain(item) else ''}
</article>"""
        )
    body = f"""<section class="hero">
  <p class="eyebrow">SEO Topic · {escape(run_date)}</p>
  <h1>{escape(label)}</h1>
  <p class="desc">{escape(description)} 当前聚合 {len(items)} 条，优先展示一周内可跟进的高价值热点。</p>
</section>
<section class="grid-3 landing-section">
  <article><p class="kicker">适合谁看</p><h2>创作者和编辑</h2><p>用于快速判断这个主题最近有没有连续发酵的主线，避免只盯单条热搜。</p></article>
  <article><p class="kicker">更新逻辑</p><h2>7 天窗口滚动</h2><p>页面会随着采集任务滚动刷新，保留近期重复出现、来源较明确、适合继续跟进的条目。</p></article>
  <article><p class="kicker">使用方式</p><h2>先筛题再核实</h2><p>先看摘要、讨论焦点和上榜依据，正式发布前再打开详情页里的原始来源核对。</p></article>
</section>
<section class="grid-2 landing-section">
  {cluster_keyword_section_html(cluster)}
  {cluster_internal_links_html(cluster)}
</section>
<section class="list">
  {''.join(cards) if cards else '<article><p>暂无足够数据，稍后刷新。</p></article>'}
</section>"""
    structured_payload = [
        topic_item_list_jsonld(items, title, canonical),
        breadcrumb_jsonld([("首页", page_url("")), ("专题聚合", page_url("topics/index.html")), (label, canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured_payload)


def build_seo_cluster_pages(ranked_payload: dict[str, object], windows_payload: dict[str, object]) -> list[dict[str, object]]:
    pages: list[dict[str, object]] = []
    run_date = str(ranked_payload.get("run_date") or "")
    for cluster in SEO_TOPIC_CLUSTERS:
        items = collect_cluster_items(ranked_payload, windows_payload, cluster)
        if not items:
            continue
        pages.append(
            {
                "slug": cluster["slug"],
                "label": cluster["label"],
                "description": cluster["description"],
                "path": seo_cluster_page_name(str(cluster["slug"])),
                "items": items,
                "html": render_seo_cluster_page(cluster, items, run_date),
            }
        )
    return pages


def render_seo_cluster_index(pages: list[dict[str, object]], run_date: str) -> str:
    cards = []
    for page in pages:
        items = page.get("items") if isinstance(page.get("items"), list) else []
        sample = items[0] if items else {}
        cluster = next((row for row in SEO_TOPIC_CLUSTERS if row.get("slug") == page.get("slug")), {})
        keywords = "、".join(cluster_intent_keywords(cluster, 4))
        cards.append(
            f"""<article>
  <h2><a href="/{escape(str(page.get("path") or ""))}">{escape(str(page.get("label") or ""))}</a></h2>
  <div class="meta"><span class="pill">7天聚合</span><span class="pill">{len(items)} 条</span></div>
  <p>{escape(str(page.get("description") or ""))}</p>
  {f'<p class="source">承接搜索词：{escape(keywords)}</p>' if keywords else ''}
  {f'<p class="source">最新样例：{escape(str(sample.get("title") or ""))}</p>' if sample else ''}
</article>"""
        )
    title = "热点专题聚合 | RDXW 热点雷达"
    description = "RDXW 热点雷达按中超、NBA、欧冠、电竞转会、AI产品、AI智能体、GitHub AI项目等主题聚合一周热点，方便创作者按专题找持续发酵主线。"
    canonical = page_url("topics/index.html")
    body = f"""<section class="hero">
  <p class="eyebrow">Topic Clusters · {escape(run_date)}</p>
  <h1>热点专题聚合</h1>
  <p class="desc">{escape(description)}</p>
</section>
<section class="list">
  {''.join(cards) if cards else '<article><p>暂无专题数据。</p></article>'}
</section>"""
    return static_page_shell(title, description, canonical, body, breadcrumb_jsonld([("首页", page_url("")), ("专题聚合", canonical)]))


def render_rss_feed(ranked_payload: dict[str, object]) -> str:
    generated = parse_ranked_timestamp(ranked_payload.get("reference_time")) or datetime.now().astimezone()
    items = [item for item in ranked_payload.get("items", []) if isinstance(item, dict)][:60]
    rows = []
    for item in items:
        title = str(item.get("title") or "")
        link = item_detail_url(item) or SITE_BASE_URL
        pub_dt = parse_ranked_timestamp(item.get("latest_published_at") or item.get("published_at")) or generated
        pub = pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        desc = item_summary(item)
        guid = link or f"{SITE_BASE_URL}/#{normalize_title(title)}"
        rows.append(
            f"""<item>
  <title>{escape(title)}</title>
  <link>{escape(link)}</link>
  <guid isPermaLink="false">{escape(guid)}</guid>
  <pubDate>{escape(pub)}</pubDate>
  <category>{escape(str(item.get("topic_label") or item.get("topic") or ""))}</category>
  <source url="{escape(SITE_BASE_URL)}/">RDXW 热点雷达</source>
  <description>{escape(desc)}</description>
</item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>RDXW 热点雷达</title>
  <link>{escape(SITE_BASE_URL)}/</link>
  <atom:link href="{escape(SITE_BASE_URL)}/feed.xml" rel="self" type="application/rss+xml" />
  <description>体育、电竞、AI、娱乐、平台热议与 GitHub 多频道热点。天气和黄历由私域推送侧另行拼接，不属于 RSS 数据源。</description>
  <language>zh-CN</language>
  <generator>RDXW Hotspot Radar</generator>
  <docs>https://www.rssboard.org/rss-specification</docs>
  <ttl>30</ttl>
  <lastBuildDate>{escape(generated.strftime("%a, %d %b %Y %H:%M:%S %z"))}</lastBuildDate>
  {''.join(rows)}
</channel>
</rss>
"""


def render_sitemap(urls: list[tuple[str, str]]) -> str:
    rows = "\n".join(
        f"  <url>\n    <loc>{escape(loc)}</loc>\n    <lastmod>{escape(lastmod)}</lastmod>\n  </url>"
        for loc, lastmod in urls
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{rows}
</urlset>
"""


def render_sitemap_index(sitemaps: list[tuple[str, str]]) -> str:
    rows = "\n".join(
        f"  <sitemap>\n    <loc>{escape(loc)}</loc>\n    <lastmod>{escape(lastmod)}</lastmod>\n  </sitemap>"
        for loc, lastmod in sitemaps
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{rows}
</sitemapindex>
"""


def render_sitemap_txt(urls: list[tuple[str, str]]) -> str:
    return "\n".join(loc for loc, _lastmod in urls) + "\n"


def dedupe_sitemap_urls(urls: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for loc, lastmod in urls:
        if not loc or loc in seen:
            continue
        seen.add(loc)
        result.append((loc, lastmod))
    return result


def daily_archive_sitemap_urls(site_root: Path, fallback_lastmod: str) -> list[tuple[str, str]]:
    daily_dir = site_root / "daily"
    urls: list[tuple[str, str]] = []
    if not daily_dir.exists():
        return urls
    for path in sorted(daily_dir.glob("*.html")):
        date_part = path.stem
        lastmod = date_part if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part) else fallback_lastmod
        urls.append((page_url(f"daily/{path.name}"), lastmod))
    return urls


def refresh_daily_archive_meta(site_root: Path) -> int:
    daily_dir = site_root / "daily"
    if not daily_dir.exists():
        return 0
    changed = 0
    for path in daily_dir.glob("*.html"):
        run_date = path.stem
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_date):
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except OSError:
            continue
        count_match = re.search(r"共\s*(\d+)\s*条", html)
        count = count_match.group(1) if count_match else "多"
        description = meta_description(
            f"{run_date} RDXW 多频道热点日报，共 {count} 条，覆盖体育、电竞、AI、娱乐、平台热议和 GitHub，提供摘要、来源核对、热度信号和自媒体选题切口。",
            fallback=f"{run_date} 热点日报",
        )
        new_html = re.sub(
            r'(<meta\s+name="description"\s+content=")[^"]*("\s*/?>)',
            lambda m: f'{m.group(1)}{escape(description)}{m.group(2)}',
            html,
            count=1,
        )
        new_html = re.sub(
            r'(<meta\s+property="og:description"\s+content=")[^"]*("\s*/?>)',
            lambda m: f'{m.group(1)}{escape(description)}{m.group(2)}',
            new_html,
            count=1,
        )
        new_html = re.sub(
            r'(<meta\s+name="twitter:description"\s+content=")[^"]*("\s*/?>)',
            lambda m: f'{m.group(1)}{escape(description)}{m.group(2)}',
            new_html,
            count=1,
        )
        new_html = re.sub(
            rf"<p class=\"desc\">{re.escape(run_date)}\s*多频道热点日报，共\s*\d+\s*条。</p>",
            f'<p class="desc">{escape(description)}</p>',
            new_html,
            count=1,
        )
        if new_html != html:
            path.write_text(new_html, encoding="utf-8")
            changed += 1
    return changed


def build_search_console_priority_urls(
    ranked_payload: dict[str, object],
    cluster_pages: list[dict[str, object]],
    daily_name: str,
    weekly_name: str,
    limit: int = 20,
) -> list[dict[str, str]]:
    run_date = str(ranked_payload.get("run_date") or "")
    candidates: list[tuple[str, str, str]] = [
        (page_url(""), "首页", "全站入口，含主榜、频道入口和重点专题内链"),
        (page_url("creator-topics.html"), "自媒体选题页", "承接创作者搜索意图"),
        (page_url("today-sports-hotspots.html"), "体育热点落地页", "体育主词入口"),
        (page_url("esports-hotspot-daily.html"), "电竞热点落地页", "电竞主词入口"),
        (page_url("ai-hotspot-tracker.html"), "AI 热点落地页", "AI 主词入口"),
        (page_url("weekly/index.html"), "本周热点报告", "周报型可引用资产"),
        (page_url("methodology.html"), "筛选方法论", "解释站点如何产生独特价值"),
        (page_url("api.html"), "API 与嵌入页", "便于工具站和外部站引用"),
        (page_url("sports.html"), "体育 7 天榜", "频道核心页"),
        (page_url("esports.html"), "电竞 7 天榜", "频道核心页"),
        (page_url("ai.html"), "AI 7 天榜", "频道核心页"),
        (page_url("topics/index.html"), "专题聚合首页", "专题内链入口"),
        (page_url(daily_name), f"{run_date} 热点日报", "当日归档页"),
        (page_url(weekly_name), "本周热点报告归档", "稳定周报 URL"),
    ]
    for page in cluster_pages:
        path = str(page.get("path") or "")
        label = str(page.get("label") or "")
        if path:
            candidates.append((page_url(path), label, "7 天专题聚合页，适合人工请求索引"))
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for url, label, reason in candidates:
        if url in seen:
            continue
        seen.add(url)
        rows.append({"url": url, "label": label, "reason": reason})
        if len(rows) >= limit:
            break
    return rows


def render_llms_txt(manifest: dict[str, object], ranked_payload: dict[str, object]) -> str:
    generated = str(manifest.get("generated_at") or ranked_payload.get("reference_time") or "")
    topics = ", ".join(str(topic.get("label") or topic.get("key")) for topic in manifest.get("topics", []) if isinstance(topic, dict))
    return f"""# RDXW 热点雷达

RDXW 热点雷达是中文多频道热点聚合站，覆盖：{topics}。

更新时间：{generated}
首页：{SITE_BASE_URL}/
RSS：{SITE_BASE_URL}/feed.xml
Manifest：{SITE_BASE_URL}/output/latest_hotspots_manifest.json
频道 JSON：{SITE_BASE_URL}/output/topics/{{window}}_{{topic}}.json
来源质量：{SITE_BASE_URL}/output/source_quality.json
健康检查：{SITE_BASE_URL}/output/health.json
AI 上下文：{SITE_BASE_URL}/ai-context.txt
专题聚合：{SITE_BASE_URL}/topics/index.html
每周报告：{SITE_BASE_URL}/weekly/index.html
筛选方法：{SITE_BASE_URL}/methodology.html
API 与嵌入：{SITE_BASE_URL}/api.html
可用窗口：1d、3d、7d
默认频道页：{SITE_BASE_URL}/sports.html

推荐引用顺序：
1. 热点详情页：用于引用单条热点，包含摘要、来源、讨论焦点、选题切口和原始来源。
2. 专题聚合页：用于引用中超、NBA、电竞转会、AI 产品、GitHub 项目等持续主题。
3. 静态频道页：用于引用 24 小时、3 天、7 天窗口榜单。
4. RSS：用于订阅最新更新。
5. JSON 接口：仅供机器读取，不建议作为公开引用页。

引用边界：广告、合作推广、按钮文案和跳转链接不属于新闻主题，不要写入热点摘要或站点主题。
"""


def render_ai_context_txt(manifest: dict[str, object], ranked_payload: dict[str, object]) -> str:
    generated = str(manifest.get("generated_at") or ranked_payload.get("reference_time") or "")
    labels = ranked_payload.get("topic_labels", {}) if isinstance(ranked_payload.get("topic_labels"), dict) else {}
    counts = ranked_payload.get("topic_counts", {}) if isinstance(ranked_payload.get("topic_counts"), dict) else {}
    topic_lines = []
    for topic in ALL_TOPICS:
        topic_lines.append(f"- {labels.get(topic) or topic}: {counts.get(topic, 0)} 条，频道页 {SITE_BASE_URL}/{topic_page_name(topic, '7d')}")
    top_lines = []
    for item in [row for row in ranked_payload.get("items") or [] if isinstance(row, dict)][:12]:
        top_lines.append(
            f"- {item.get('title')}｜{item.get('topic_label') or item.get('topic')}｜{item.get('source') or '未知来源'}｜"
            f"{item.get('trend_label') or item_trend_label(item)}｜{item.get('detail_url') or item_detail_url(item)}"
        )
    return f"""RDXW 热点雷达 AI Context

站点：{SITE_BASE_URL}/
定位：中文热点采集与自媒体选题雷达，重点覆盖体育、电竞、AI、娱乐、平台热议与 GitHub。
更新时间：{generated}
数据接口：
- 最新主榜：{SITE_BASE_URL}/output/latest_hotspots_ranked.json
- 7 天窗口：{SITE_BASE_URL}/output/latest_hotspots_windows.json
- 来源质量：{SITE_BASE_URL}/output/source_quality.json
- 每日推送：{SITE_BASE_URL}/output/latest_daily_brief.json
- 健康检查：{SITE_BASE_URL}/output/health.json
- 专题聚合：{SITE_BASE_URL}/topics/index.html
- 每周报告：{SITE_BASE_URL}/weekly/index.html
- 筛选方法：{SITE_BASE_URL}/methodology.html
- API 与嵌入：{SITE_BASE_URL}/api.html

频道：
{chr(10).join(topic_lines)}

推荐引用顺序：
- 单条热点优先引用站内详情页。
- 连续主题优先引用专题聚合页。
- 今日或本周列表优先引用频道页、日报页或 RSS。
- JSON 接口仅供机器读取，不作为面向读者的引用页。

内容边界：
- 广告、合作推广、按钮文案和跳转链接不属于热点内容。
- 本站用于选题初筛；事实核对以详情页中的原始来源为准。

最新热点样例：
{chr(10).join(top_lines)}

引用建议：优先引用站内详情页；需要核实时再打开 original_url 或详情页中的原始来源。
"""


def clean_public_items(items: list[dict[str, object]], limit: int = 12) -> list[dict[str, object]]:
    cleaned: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = enrich_item_for_publication(raw)
        key = str(item.get("detail_path") or item.get("hotspot_id") or stable_item_id(item) or item.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


def topic_items_from_payloads(
    ranked_payload: dict[str, object],
    topic_payloads: dict[tuple[str, str], dict[str, object]] | None,
    topic: str,
    limit: int = 12,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    payload = (topic_payloads or {}).get(("7d", topic)) or {}
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items.extend(row for row in payload.get("items") or [] if isinstance(row, dict))
    if len(items) < limit:
        items.extend(
            row
            for row in ranked_payload.get("items") or []
            if isinstance(row, dict) and str(row.get("topic") or "") == topic
        )
    return clean_public_items(items, limit)


def rank_list_html(items: list[dict[str, object]], limit: int = 8, show_summary: bool = True) -> str:
    rows = []
    for idx, item in enumerate(items[:limit], 1):
        link = item_detail_url(item) or "#"
        title = str(item.get("title") or "")
        meta = " · ".join(
            v
            for v in [
                str(item.get("trend_label") or item_trend_label(item)),
                str(item.get("source") or ""),
                item_source_domain(item),
            ]
            if v
        )
        summary = item_summary(item)
        rows.append(
            f"""<li>
  <span class="rank-num">{idx}</span>
  <span><a class="rank-title" href="{escape(link)}">{escape(title)}</a>{f'<span class="rank-desc">{escape(meta)}</span>' if meta else ''}{f'<span class="rank-desc">{escape(summary[:96])}</span>' if show_summary and summary else ''}</span>
</li>"""
        )
    return '<ol class="rank-list">' + "".join(rows or ["<li>暂无数据</li>"]) + "</ol>"


def stable_landing_specs() -> list[dict[str, object]]:
    return [
        {
            "path": "today-sports-hotspots.html",
            "topic": "sports",
            "label": "体育热点",
            "title": "今日体育热点榜 | 体育新闻热点与自媒体选题",
            "h1": "今日体育热点榜",
            "description": "RDXW 每 3 小时更新体育新闻热点，优先聚合中超、CBA、NBA、欧冠、WTT、国乒和中国球员相关赛果、伤病、转会与争议，适合自媒体做赛后复盘和人物切口。",
            "promise": "优先保留国内赛事、中国球员、强赛果和一周内持续发酵的体育主线。",
            "angles": ["赛后复盘", "关键人物", "下一场走势", "争议判罚", "伤病影响"],
        },
        {
            "path": "esports-hotspot-daily.html",
            "topic": "esports",
            "label": "电竞热点",
            "title": "电竞热点日报 | LPL KPL CS2 无畏契约自媒体选题",
            "h1": "电竞热点日报",
            "description": "RDXW 聚合 LPL、KPL、CS2、无畏契约、战队阵容、转会续约和俱乐部动态，适合做电竞社区选题、赛程前瞻、赛后复盘与选手话题跟进。",
            "promise": "把赛事、选手、俱乐部、版本和商业动态放到同一层，减少只看单条热搜造成的误判。",
            "angles": ["赛程前瞻", "战队复盘", "选手话题", "版本变化", "转会阵容"],
        },
        {
            "path": "ai-hotspot-tracker.html",
            "topic": "ai",
            "label": "AI热点",
            "title": "AI热点追踪 | 大模型 产品 Agent 与开源项目日报",
            "h1": "AI热点追踪",
            "description": "RDXW 追踪 AI 大模型、产品更新、Agent、开发者工具、监管争议和 GitHub 开源项目热度，优先筛掉泛 PR，保留更适合创作者解读的信号。",
            "promise": "不把所有 AI 新闻都堆上来，优先保留模型、产品、工具和争议主线。",
            "angles": ["产品更新", "Agent 落地", "工具效率", "开源项目", "商业化争议"],
        },
    ]


def render_stable_landing_page(spec: dict[str, object], items: list[dict[str, object]], run_date: str) -> str:
    topic = str(spec.get("topic") or "")
    label = str(spec.get("label") or "")
    title = str(spec.get("title") or label)
    h1 = str(spec.get("h1") or label)
    description = str(spec.get("description") or "")
    canonical_path = str(spec.get("path") or "")
    canonical = page_url(canonical_path)
    angles = [str(v) for v in spec.get("angles") or [] if v]
    angle_html = "".join(f'<span class="pill">{escape(v)}</span>' for v in angles)
    briefing_cards = []
    for idx, item in enumerate(items[:6], 1):
        briefing = item.get("publication_briefing") if isinstance(item.get("publication_briefing"), dict) else publication_briefing(item)
        briefing_cards.append(
            f"""<article>
  <p class="kicker">#{idx} · {escape(str(item.get("trend_label") or item_trend_label(item)))}</p>
  <h2><a href="{escape(item_detail_url(item) or '#')}">{escape(str(item.get("title") or ""))}</a></h2>
  <p>{escape(str(briefing.get("what_happened") or item_summary(item)))}</p>
  <p class="source">切口：{escape(str(item.get("creator_angle") or "").removeprefix("切口：").strip() or str(briefing.get("why_it_matters") or ""))}</p>
</article>"""
        )
    body = f"""<section class="hero">
  <p class="eyebrow">RDXW SEO Landing · {escape(run_date)}</p>
  <h1>{escape(h1)}</h1>
  <p class="desc">{escape(description)}</p>
  <div class="hero-actions">
    <a class="button" href="/{escape(topic_page_name(topic, '7d'))}">查看实时榜单</a>
    <a class="button secondary" href="/creator-topics.html">看自媒体选题页</a>
  </div>
</section>
<section class="grid-3 landing-section">
  <article><p class="kicker">更新频率</p><h2>每 3 小时刷新</h2><p>公开站保留 24 小时、3 天和 7 天窗口，方便看当天爆点和一周主线。</p></article>
  <article><p class="kicker">筛选口径</p><h2>先看可创作价值</h2><p>{escape(str(spec.get("promise") or ""))}</p></article>
  <article><p class="kicker">常用切口</p><h2>直接拆成选题</h2><div class="meta">{angle_html}</div></article>
</section>
<section class="landing-section">
  <h2>当前可跟热点</h2>
  <div class="list">{''.join(briefing_cards) if briefing_cards else '<article><p>暂无足够数据，稍后刷新。</p></article>'}</div>
</section>"""
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"{h1}多久更新一次？",
                "acceptedAnswer": {"@type": "Answer", "text": "站点默认每 3 小时采集和生成一次，页面同时保留 24 小时、3 天和 7 天窗口。"},
            },
            {
                "@type": "Question",
                "name": "这些热点适合直接发布吗？",
                "acceptedAnswer": {"@type": "Answer", "text": "适合做选题雷达和初筛。正式发布前仍建议打开详情页里的原始来源核对事实。"},
            },
        ],
    }
    structured = [
        topic_item_list_jsonld(items, title, canonical),
        faq,
        breadcrumb_jsonld([("首页", page_url("")), (h1, canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured)


def render_creator_landing_page(ranked_payload: dict[str, object], topic_payloads: dict[tuple[str, str], dict[str, object]] | None) -> str:
    run_date = str(ranked_payload.get("run_date") or "")
    sports = topic_items_from_payloads(ranked_payload, topic_payloads, "sports", 6)
    esports = topic_items_from_payloads(ranked_payload, topic_payloads, "esports", 6)
    ai_items = topic_items_from_payloads(ranked_payload, topic_payloads, "ai", 6)
    top_items = clean_public_items(sports[:3] + esports[:3] + ai_items[:3], 9)
    title = "自媒体选题热点日报 | 体育电竞AI热点雷达"
    description = "RDXW 为自媒体创作者整理今日和一周内的体育、电竞、AI 热点，提供标题、摘要、来源、详情页和可拆解的选题切口。"
    canonical = page_url("creator-topics.html")
    body = f"""<section class="hero">
  <p class="eyebrow">Creator Landing · {escape(run_date)}</p>
  <h1>自媒体选题热点日报</h1>
  <p class="desc">{escape(description)}</p>
  <div class="hero-actions">
    <a class="button" href="/sports.html">看体育热点</a>
    <a class="button secondary" href="/esports.html">看电竞热点</a>
    <a class="button secondary" href="/ai.html">看 AI 热点</a>
  </div>
</section>
<section class="grid-3 landing-section">
  <article><p class="kicker">用途</p><h2>先找可拍的题</h2><p>不是单纯堆新闻，而是把强赛果、人物、争议、产品更新和持续发酵主线先筛出来。</p></article>
  <article><p class="kicker">节奏</p><h2>当天 + 一周</h2><p>当天榜适合抢速度，7 天榜适合找反复出现的主线和后续跟进内容。</p></article>
  <article><p class="kicker">核对</p><h2>详情页保留来源</h2><p>每条热点都有站内详情页和原始来源入口，发布前可以快速核对。</p></article>
</section>
<section class="grid-3 landing-section">
  <article><h2>体育可跟</h2>{rank_list_html(sports, 5, False)}</article>
  <article><h2>电竞可跟</h2>{rank_list_html(esports, 5, False)}</article>
  <article><h2>AI 可跟</h2>{rank_list_html(ai_items, 5, False)}</article>
</section>
<section class="landing-section">
  <div class="quote-box">
    <p>推荐用法：每天先看 24 小时榜抢即时热点，再看 7 天榜找可以连续做 2-3 条内容的主线。体育和电竞优先看赛果、人物、争议和下一场走势；AI 优先看产品、模型、工具和真实落地。</p>
  </div>
</section>"""
    structured = [
        {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "url": canonical,
            "inLanguage": "zh-CN",
            "description": description,
            "about": [{"@type": "Thing", "name": v} for v in ["自媒体选题", "体育热点", "电竞热点", "AI热点"]],
        },
        topic_item_list_jsonld(top_items, title, canonical),
        breadcrumb_jsonld([("首页", page_url("")), ("自媒体选题", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured)


def weekly_report_page_name(generated_dt: datetime) -> str:
    year, week, _weekday = generated_dt.isocalendar()
    return f"weekly/{year}-W{week:02d}.html"


def weekly_report_items(ranked_payload: dict[str, object], windows_payload: dict[str, object], limit: int = 36) -> list[dict[str, object]]:
    pool: list[dict[str, object]] = []
    seven_day = ((windows_payload.get("windows") or {}).get("7d") or {}).get("items") if isinstance(windows_payload, dict) else None
    if isinstance(seven_day, list):
        pool.extend(row for row in seven_day if isinstance(row, dict))
    pool.extend(row for row in ranked_payload.get("items") or [] if isinstance(row, dict))
    collected: dict[str, dict[str, object]] = {}
    for raw in pool:
        item = enrich_item_for_publication(raw)
        key = str(item.get("detail_path") or item.get("hotspot_id") or stable_item_id(item) or item.get("title") or "")
        prev = collected.get(key)
        if prev is None or numeric_score(item.get("editorial_value_score") or item.get("score")) > numeric_score(prev.get("editorial_value_score") or prev.get("score")):
            collected[key] = item
    items = list(collected.values())
    items.sort(
        key=lambda row: (
            -item_source_count(row),
            -numeric_score(row.get("editorial_value_score") or row.get("window_score") or row.get("total_score") or row.get("score")),
            str(row.get("last_seen_at") or row.get("latest_published_at") or ""),
        )
    )
    return items[:limit]


def render_methodology_page(ranked_payload: dict[str, object]) -> str:
    items = [row for row in ranked_payload.get("items") or [] if isinstance(row, dict)]
    total = len(items)
    indexed = sum(1 for item in items if detail_is_search_indexable(enrich_item_for_publication(item)))
    single_source = sum(1 for item in items if item_source_count(item) < 2)
    run_date = str(ranked_payload.get("run_date") or "")
    title = "RDXW 方法论 | 热点筛选、来源核对与收录规则"
    description = "RDXW 方法论说明热点雷达如何采集、去重、排序、筛选、生成详情页，以及为什么弱单来源热点不主动提交搜索索引。"
    canonical = page_url("methodology.html")
    body = f"""<section class="hero">
  <p class="eyebrow">Methodology · {escape(run_date)}</p>
  <h1>RDXW 怎么筛热点</h1>
  <p class="desc">{escape(description)}</p>
</section>
<section class="grid-3 landing-section">
  <article><p class="kicker">当前主榜</p><h2>{total} 条</h2><p>每轮采集会生成多频道主榜，并保留 24 小时、3 天、7 天窗口。</p></article>
  <article><p class="kicker">主动收录</p><h2>{indexed} 条</h2><p>只有 3 个以上来源交叉、极高热度强选题或 GitHub 最高热项目才进入热点 sitemap。</p></article>
  <article><p class="kicker">站内浏览</p><h2>{single_source} 条单来源</h2><p>普通单来源热点仍可在站内查看，但默认 noindex，避免把薄详情页主动推给搜索引擎。</p></article>
</section>
<section class="grid-2 landing-section">
  <article><h2>采集范围</h2><p>RDXW 覆盖体育、电竞、AI、娱乐、平台热议和 GitHub，并额外保留微博、抖音、B站、虎扑、知乎、百度热搜、IT之家、36氪、Product Hunt、豆瓣、腾讯视频等来源雷达作为旁路参考。</p></article>
  <article><h2>排序口径</h2><p>排序会综合来源质量、时间窗口、关键词、频道权重、重复出现、选题价值和编辑摘要。它不是事实裁判，正式引用前仍应打开详情页里的原始来源核对。</p></article>
  <article><h2>收录口径</h2><p>详情页分成两类：可搜索收录页和站内浏览页。3 个以上来源交叉、极高热度强选题、GitHub 最高热项目会进入 <code>sitemap-hot.xml</code>；普通单来源页保留访问但加 <code>noindex,follow</code>。</p></article>
  <article><h2>为什么这样做</h2><p>热点站最容易变成自动搬运页。RDXW 优先把可引用资产放在首页、频道页、专题页、周报页和方法论页，把低确定性的单条热点留给站内工具使用。</p></article>
</section>
<section class="grid-3 landing-section">
  <article><h2>适合引用的页面</h2><ul><li><a href="/">首页</a></li><li><a href="/creator-topics.html">自媒体选题页</a></li><li><a href="/topics/index.html">专题聚合</a></li><li><a href="/weekly/index.html">每周热点报告</a></li></ul></article>
  <article><h2>不建议外链的页面</h2><p>短期、单来源、低选题价值的详情页不适合主动做外链；它们更适合用户在站内筛题时临时打开。</p></article>
  <article><h2>引用边界</h2><p>广告、合作推广、按钮文案和跳转链接不属于热点内容；来源核对以详情页列出的原始来源为准。</p></article>
</section>"""
    structured = [
        {"@context": "https://schema.org", "@type": "WebPage", "name": title, "url": canonical, "description": description, "inLanguage": "zh-CN"},
        breadcrumb_jsonld([("首页", page_url("")), ("方法论", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured)


def render_api_page(manifest: dict[str, object], ranked_payload: dict[str, object]) -> str:
    generated = str(manifest.get("generated_at") or ranked_payload.get("reference_time") or "")
    title = "RDXW API 与嵌入 | RSS、JSON、热点组件"
    description = "RDXW 提供 RSS、公开 JSON、频道窗口数据和可嵌入热点组件，适合个人站、内容团队和自动化工作流引用热点雷达数据。"
    canonical = page_url("api.html")
    endpoints = [
        ("/feed.xml", "RSS 订阅，适合阅读器、自动化推送和内容看板。"),
        ("/output/latest_hotspots_ranked.json", "最新主榜 JSON，包含多频道热点摘要。"),
        ("/output/latest_hotspots_manifest.json", "前端 manifest，说明可用频道和窗口。"),
        ("/output/topics/7d_sports.json", "频道窗口 JSON，可替换为 1d/3d/7d 与 sports/esports/ai 等组合。"),
        ("/output/source_radar.json", "来源雷达 JSON，展示多平台热榜卡片。"),
        ("/embed/latest.html", "轻量 iframe 组件，适合外站嵌入最新热点。"),
    ]
    endpoint_rows = "".join(
        f'<li><a href="{escape(path)}">{escape(path)}</a><span> · {escape(note)}</span></li>'
        for path, note in endpoints
    )
    body = f"""<section class="hero">
  <p class="eyebrow">API · {escape(generated[:16].replace("T", " "))}</p>
  <h1>RSS、JSON 和嵌入组件</h1>
  <p class="desc">{escape(description)}</p>
</section>
<section class="grid-2 landing-section">
  <article><h2>公开入口</h2><ul>{endpoint_rows}</ul></article>
  <article><h2>外站嵌入</h2><p>推荐使用 iframe，避免跨域 JSON 限制。示例：</p><p class="source">&lt;iframe src=&quot;https://rdxw.cc/embed/latest.html&quot; width=&quot;100%&quot; height=&quot;420&quot; loading=&quot;lazy&quot;&gt;&lt;/iframe&gt;</p></article>
  <article><h2>引用要求</h2><p>引用或嵌入时保留“RDXW 热点雷达”或裸链归因。正式发布内容前，应打开详情页来源核对事实。</p></article>
  <article><h2>适合场景</h2><p>个人站热点卡片、公众号选题看板、内容团队日报、Telegram/飞书自动摘要、站长工具导航页。</p></article>
</section>"""
    structured = [
        {"@context": "https://schema.org", "@type": "TechArticle", "headline": title, "url": canonical, "description": description, "inLanguage": "zh-CN"},
        breadcrumb_jsonld([("首页", page_url("")), ("API 与嵌入", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured)


def render_feedback_page() -> str:
    title = "RDXW 反馈与建议 | 功能建议、Bug 与热点源需求"
    description = "向 RDXW 热点雷达提交功能建议、Bug、数据不准、想看的热点来源或合作反馈，帮助热点雷达持续优化。"
    canonical = page_url("feedback.html")
    body = f"""<section class="hero">
  <p class="eyebrow">Feedback Loop</p>
  <h1>反馈、建议和想看的热点源</h1>
  <p class="desc">{escape(description)}</p>
  <div class="hero-actions">
    <a class="button" href="#feedbackForm">填写反馈</a>
    <a class="button secondary" href="/methodology.html">查看筛选方法</a>
  </div>
</section>
<section class="grid-2 landing-section">
  <article>
    <h2>可以反馈什么</h2>
    <ul>
      <li>想新增的热点源：例如微博、抖音、Reddit、YouTube、某个赛事站或开发者社区。</li>
      <li>榜单不准：标题低质、来源重复、分类错误、热度排序不合理。</li>
      <li>Bug：页面打不开、数据没更新、链接错误、手机端显示异常。</li>
      <li>功能建议：提醒、订阅、筛选、导出、API、iframe、周报格式。</li>
      <li>合作反馈：希望在自己的站点、频道或内容工作流里使用 RDXW。</li>
    </ul>
  </article>
  <article>
    <h2>为什么要听反馈</h2>
    <p>热点雷达不是一次性页面工程。真正有用的部分来自持续迭代：哪些来源值得接入、哪些标题应该降噪、哪些频道需要更细的筛选，都需要真实用户反馈来校正。</p>
  </article>
</section>
<section class="landing-section">
  <article>
    <h2>提交反馈</h2>
    <form class="feedback-form" id="feedbackForm">
      <label>反馈类型
        <select id="feedbackType" name="type">
          <option>功能建议</option>
          <option>Bug 修复</option>
          <option>数据不准</option>
          <option>想看新的热点源</option>
          <option>频道或专题建议</option>
          <option>合作或嵌入需求</option>
          <option>其他</option>
        </select>
      </label>
      <label>相关页面
        <input id="feedbackUrl" name="url" type="url" placeholder="https://rdxw.cc/..." />
      </label>
      <label>具体说明
        <textarea id="feedbackMessage" name="message" placeholder="例如：希望增加 Reddit / YouTube 某个频道；某条热点分类不准；手机端某个按钮不好点。"></textarea>
      </label>
      <label>联系方式
        <input id="feedbackContact" name="contact" type="text" placeholder="邮箱、X、Telegram 或其他联系方式，可不填" />
      </label>
      <label class="hp-field" aria-hidden="true">公司
        <input id="feedbackCompany" name="company" type="text" tabindex="-1" autocomplete="off" />
      </label>
      <div class="hero-actions">
        <button class="button" id="feedbackSubmit" type="submit">提交反馈</button>
      </div>
      <p class="help-text">提交后会直接保存到 RDXW 服务器的反馈列表，不需要登录，也不需要打开邮箱。联系方式可不填；如果填写，只用于后续沟通。</p>
      <p class="help-text" id="feedbackStatus" role="status" aria-live="polite"></p>
    </form>
  </article>
</section>
<script>
(function(){{
  const form = document.getElementById("feedbackForm");
  const urlInput = document.getElementById("feedbackUrl");
  if (urlInput && document.referrer && document.referrer.startsWith(location.origin)) {{
    urlInput.value = document.referrer;
  }}
  if (!form) return;
  form.addEventListener("submit", function(event) {{
    event.preventDefault();
    const submit = document.getElementById("feedbackSubmit");
    const status = document.getElementById("feedbackStatus");
    const type = document.getElementById("feedbackType").value.trim();
    const url = document.getElementById("feedbackUrl").value.trim();
    const message = document.getElementById("feedbackMessage").value.trim();
    const contact = document.getElementById("feedbackContact").value.trim();
    const company = document.getElementById("feedbackCompany").value.trim();
    if (!message || message.length < 5) {{
      status.textContent = "请至少写几句话，说明你遇到的问题或建议。";
      return;
    }}
    submit.disabled = true;
    status.textContent = "正在提交...";
    fetch("/api/feedback", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{type, url, message, contact, company, page: location.href}})
    }})
      .then(function(response) {{
        return response.json().catch(function() {{ return {{ok: false, error: "bad_response"}}; }});
      }})
      .then(function(data) {{
        if (data && data.ok) {{
          form.reset();
          status.textContent = "已收到，感谢反馈。";
        }} else {{
          status.textContent = "提交失败，请稍后再试。";
        }}
      }})
      .catch(function() {{
        status.textContent = "提交失败，请稍后再试。";
      }})
      .finally(function() {{
        submit.disabled = false;
      }});
  }});
}})();
</script>"""
    structured = [
        {"@context": "https://schema.org", "@type": "ContactPage", "name": title, "url": canonical, "description": description, "inLanguage": "zh-CN"},
        breadcrumb_jsonld([("首页", page_url("")), ("反馈建议", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured, robots="noindex,follow")


def render_embed_latest_page(ranked_payload: dict[str, object]) -> str:
    items = clean_public_items([row for row in ranked_payload.get("items") or [] if isinstance(row, dict)], 8)
    rows = []
    for idx, item in enumerate(items, 1):
        rows.append(
            f"""<li><span>{idx}</span><a href="{escape(item_detail_url(item) or page_url(''))}" target="_blank" rel="noopener">{escape(str(item.get("title") or ""))}</a><small>{escape(str(item.get("topic_label") or item.get("topic") or ""))} · {escape(str(item.get("source") or ""))}</small></li>"""
        )
    title = "RDXW 最新热点组件"
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex,follow" />
  <title>{escape(title)}</title>
  <style>
    *{{box-sizing:border-box}}body{{margin:0;background:#fff;color:#111114;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}.box{{border:1px solid rgba(15,23,42,.12);border-radius:14px;padding:14px;background:#fff}}h1{{font-size:18px;margin:0 0 10px}}ol{{display:grid;gap:10px;margin:0;padding:0;list-style:none}}li{{display:grid;grid-template-columns:24px 1fr;gap:8px;align-items:start}}span{{width:24px;height:24px;border-radius:50%;background:#eef3ff;color:#0071e3;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800}}a{{color:#111114;text-decoration:none;font-weight:700;line-height:1.35}}small{{grid-column:2;color:#6e6e73;font-size:12px}}footer{{margin-top:12px;font-size:12px;color:#6e6e73}}footer a{{color:#0071e3}}
  </style>
</head>
<body><section class="box"><h1>RDXW 最新热点</h1><ol>{''.join(rows)}</ol><footer>来源：<a href="{escape(SITE_BASE_URL)}/" target="_blank" rel="noopener">RDXW 热点雷达</a></footer></section></body>
</html>"""
    return body


def render_weekly_report_page(
    ranked_payload: dict[str, object],
    windows_payload: dict[str, object],
    generated_dt: datetime,
    canonical_path: str,
) -> str:
    items = weekly_report_items(ranked_payload, windows_payload, 36)
    year, week, _weekday = generated_dt.isocalendar()
    grouped: dict[str, list[dict[str, object]]] = {topic: [] for topic in ALL_TOPICS}
    for item in items:
        grouped.setdefault(str(item.get("topic") or "sports"), []).append(item)
    multi_source = [item for item in items if item_source_count(item) >= 2]
    strong = [item for item in items if str(item.get("editorial_value_level") or "") == "强选题"]
    is_weekly_index = canonical_path.rstrip("/") == "weekly/index.html"
    if is_weekly_index:
        title = "RDXW 每周热点报告索引 | 体育电竞AI热点周报归档"
        description = "RDXW 每周热点报告索引汇总最新 7 天体育、电竞、AI、娱乐、平台热议和 GitHub 热点周报，方便回看持续主线、多源交叉热点和自媒体选题方向。"
        eyebrow = "Weekly Reports"
        h1 = "每周热点报告索引"
    else:
        title = f"RDXW 每周热点报告 {year}W{week:02d} | 体育电竞AI选题复盘"
        description = "RDXW 每周热点报告汇总 7 天内体育、电竞、AI、娱乐、平台热议和 GitHub 的持续主线、多源交叉热点和自媒体选题方向。"
        eyebrow = f"Weekly Report · {year}W{week:02d}"
        h1 = "本周热点报告"
    canonical = page_url(canonical_path)
    topic_sections = []
    for topic in ALL_TOPICS:
        topic_items = grouped.get(topic, [])[:5]
        if not topic_items:
            continue
        topic_sections.append(
            f"""<article><h2>{escape(PUBLIC_TOPIC_LABELS.get(topic, topic))}</h2>{rank_list_html(topic_items, 5, True)}</article>"""
        )
    top_cross = "".join(
        f'<li><a href="{escape(item_detail_url(item) or "#")}">{escape(str(item.get("title") or ""))}</a><span> · {item_source_count(item)} 个来源</span></li>'
        for item in multi_source[:8]
    ) or "<li>本周多源交叉热点不足，建议以频道页和专题页为主。</li>"
    top_strong = "".join(
        f'<li><a href="{escape(item_detail_url(item) or "#")}">{escape(str(item.get("title") or ""))}</a><span> · {escape(str(item.get("trend_label") or ""))}</span></li>'
        for item in strong[:8]
    ) or "<li>暂无足够强选题样本。</li>"
    body = f"""<section class="hero">
  <p class="eyebrow">{escape(eyebrow)}</p>
  <h1>{escape(h1)}</h1>
  <p class="desc">{escape(description)}</p>
  <div class="hero-actions"><a class="button" href="/creator-topics.html">看今日选题</a><a class="button secondary" href="/methodology.html">查看筛选方法</a></div>
</section>
<section class="grid-3 landing-section">
  <article><p class="kicker">本周样本</p><h2>{len(items)} 条</h2><p>从 7 天窗口和最新主榜中去重后生成。</p></article>
  <article><p class="kicker">多源交叉</p><h2>{len(multi_source)} 条</h2><p>这些更适合被搜索收录、引用和继续跟进。</p></article>
  <article><p class="kicker">强选题</p><h2>{len(strong)} 条</h2><p>优先适合自媒体拆解、复盘或做系列跟进。</p></article>
</section>
<section class="grid-2 landing-section">
  <article><h2>多源交叉热点</h2><ul>{top_cross}</ul></article>
  <article><h2>强选题候选</h2><ul>{top_strong}</ul></article>
</section>
<section class="grid-3 landing-section">
  {''.join(topic_sections)}
</section>"""
    structured = [
        topic_item_list_jsonld(items, title, canonical),
        breadcrumb_jsonld([("首页", page_url("")), ("每周报告", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured)


def render_home_static_page(
    ranked_payload: dict[str, object],
    topic_payloads: dict[tuple[str, str], dict[str, object]] | None = None,
    canonical_path: str = "",
) -> str:
    labels = ranked_payload.get("topic_labels", {}) if isinstance(ranked_payload.get("topic_labels"), dict) else {}
    counts = ranked_payload.get("topic_counts", {}) if isinstance(ranked_payload.get("topic_counts"), dict) else {}
    items = [item for item in ranked_payload.get("items") or [] if isinstance(item, dict)]
    run_date = str(ranked_payload.get("run_date") or "")
    top_items = clean_public_items(items, 12)
    cards = []
    for topic in ALL_TOPICS:
        topic_items = topic_items_from_payloads(ranked_payload, topic_payloads, topic, 5)
        label = str(labels.get(topic) or topic)
        cards.append(
            f"""<article>
  <h2><a href="/{escape(topic_page_name(topic, '7d'))}">{escape(label)}</a></h2>
  <div class="meta"><span class="pill">7天窗口</span><span class="pill">{escape(str(counts.get(topic, 0)))} 条</span></div>
  {rank_list_html(topic_items, 5, False)}
</article>"""
        )
    cluster_links = cluster_cards_html(SEO_TOPIC_CLUSTERS[:10], compact=True)
    featured_clusters = cluster_cards_html(SEO_TOPIC_CLUSTERS[:6])
    cards.append(
        f"""<article>
  <h2><a href="/topics/index.html">热点专题聚合</a></h2>
  <div class="meta"><span class="pill">SEO/GEO</span><span class="pill">{len(SEO_TOPIC_CLUSTERS)} 个主题</span></div>
  {cluster_links}
</article>"""
    )
    title = "RDXW 热点雷达 | 今日体育电竞AI热点榜与自媒体选题"
    description = "RDXW 热点雷达每 3 小时更新体育、电竞、AI、娱乐、平台热议和 GitHub 热点，提供 24 小时、3 天、7 天榜单、详情页、来源核对和自媒体选题切口。"
    canonical = page_url(canonical_path)
    body = f"""<section class="hero">
  <p class="eyebrow">RDXW Hotspot Radar · {escape(run_date)}</p>
  <h1>今日热点，先筛选题。</h1>
  <p class="desc">{escape(description)}</p>
  <div class="hero-actions">
    <a class="button" href="/creator-topics.html">自媒体选题入口</a>
    <a class="button secondary" href="/sports.html">体育热点</a>
    <a class="button secondary" href="/esports.html">电竞热点</a>
    <a class="button secondary" href="/ai.html">AI 热点</a>
    <a class="button secondary" href="/weekly/index.html">本周报告</a>
    <a class="button secondary" href="/methodology.html">筛选方法</a>
  </div>
</section>
<section class="landing-section">
  <article>
    <p class="kicker">AI Search Brief</p>
    <h2>RDXW 热点雷达是什么?</h2>
    <p>RDXW 热点雷达是一个中文多来源热点聚合与自媒体选题工具，每 3 小时更新体育、电竞、AI、娱乐、平台热议和 GitHub 项目。它把 24 小时、3 天、7 天窗口分开展示，并结合微博、抖音、B站、虎扑、知乎、百度热搜、IT之家、36氪、GitHub、Product Hunt 等来源作为旁路参考。RDXW 的重点不是复制单个平台热搜，而是帮助创作者先看多源交叉、持续发酵、强选题和可核对来源，再决定是否写成短视频、图文、播客或周报。</p>
    <p lang="en">RDXW Hotspot Radar is a Chinese trend monitoring page for creators, editors, and growth operators who need fast topic discovery. The site refreshes every three hours and separates sports, esports, AI, entertainment, platform discussion, and GitHub signals into 24-hour, 3-day, and 7-day windows. It combines current ranking pages with source radar cards from Weibo, Douyin, Bilibili, Hupu, Zhihu, Baidu Hot Search, IT Home, 36Kr, GitHub Trending, Product Hunt, Douban, and Tencent Video. RDXW is not a primary news publisher; it is a filtering layer that helps users find multi-source topics, check original sources, identify creator angles, and decide whether a story deserves a short video, article, podcast segment, weekly report, or deeper manual research. Pages with stronger cross-source evidence are kept indexable, while weaker single-source detail pages remain available for browsing but are not pushed to search engines.</p>
    <div class="meta" style="margin-top:14px"><span class="pill">Updated {escape(run_date)}</span><span class="pill">Reviewed by RDXW team</span><span class="pill">多来源核对</span></div>
  </article>
</section>
<section class="grid-2 landing-section">
  <article><h2>今日主榜</h2>{rank_list_html(top_items, 8, True)}</article>
  <article><h2>为什么适合创作者</h2><p>它不只看当天热搜，还保留一周窗口、来源交叉、摘要、选题切口和详情页。你可以先用它找值得做的题，再打开原始来源核对。</p><div class="meta" style="margin-top:14px"><span class="pill">体育电竞优先</span><span class="pill">24小时 / 3天 / 7天</span><span class="pill">站内详情页</span><span class="pill">RSS / sitemap</span></div></article>
</section>
<section class="grid-3 landing-section">
  <article><p class="kicker">本周必看</p><h2>专题优先抓主线</h2><p>这些页面比单条热点更适合被搜索和 AI 摘要引用，也更适合人工提交索引。</p></article>
  {featured_clusters}
</section>
<section class="list">
  {''.join(cards)}
</section>"""
    structured = [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "RDXW 热点雷达",
            "url": SITE_BASE_URL,
            "inLanguage": "zh-CN",
            "description": description,
        },
        topic_item_list_jsonld(top_items, title, canonical),
        breadcrumb_jsonld([("首页", canonical)]),
    ]
    return static_page_shell(title, description, canonical, body, structured)


def build_health_payload(
    output_dir: Path,
    raw_payload: dict[str, object],
    ranked_payload: dict[str, object],
    windows_payload: dict[str, object],
    query_stats: list[dict[str, object]],
    source_radar_payload: dict[str, object] | None,
    static_outputs: dict[str, object],
    reference_time: datetime,
) -> dict[str, object]:
    warnings: list[str] = []
    errors = [row for row in query_stats if isinstance(row, dict) and row.get("error")]
    topic_counts = ranked_payload.get("topic_counts", {}) if isinstance(ranked_payload.get("topic_counts"), dict) else {}
    for topic in ALL_TOPICS:
        if int(topic_counts.get(topic) or 0) == 0:
            warnings.append(f"{topic} 当前没有入选热点")
    if errors:
        warnings.append(f"{len(errors)} 个查询失败")
    ranked_total = len([item for item in ranked_payload.get("items") or [] if isinstance(item, dict)])
    if ranked_total < len(ALL_TOPICS) * 5:
        warnings.append("主榜入选数量偏少")
    radar_failed = 0
    radar_ok = 0
    if source_radar_payload and isinstance(source_radar_payload.get("sources"), list):
        for source in source_radar_payload.get("sources") or []:
            if not isinstance(source, dict):
                continue
            if source.get("items"):
                radar_ok += 1
            else:
                radar_failed += 1
        if source_radar_payload.get("stale"):
            warnings.append("来源雷达使用了上一次可用快照")
    if radar_ok == 0:
        warnings.append("来源雷达当前没有可用来源")
    llm_status: dict[str, object] = {}
    llm_status_path = output_dir / "llm_editorial_status.json"
    if llm_status_path.exists():
        try:
            loaded_llm_status = json.loads(llm_status_path.read_text(encoding="utf-8"))
            if isinstance(loaded_llm_status, dict):
                llm_status = loaded_llm_status
        except Exception:
            llm_status = {"enabled": False, "error": "invalid llm status json"}
    llm_errors = llm_status.get("errors") or []
    llm_degraded_reason = str(llm_status.get("degraded_reason") or "")
    llm_known_non_core_failure = bool(llm_degraded_reason) or any(llm_error_is_known_non_core(error) for error in llm_errors)
    if llm_status.get("enabled") and llm_errors and not llm_known_non_core_failure:
        warnings.append("LLM 编辑层有部分请求失败")
    windows = windows_payload.get("windows") if isinstance(windows_payload, dict) else {}
    window_counts = {}
    if isinstance(windows, dict):
        for key, value in windows.items():
            if isinstance(value, dict):
                window_counts[key] = len(value.get("items") or []) if isinstance(value.get("items"), list) else 0
    return {
        "ok": not errors and ranked_total > 0,
        "generated_at": reference_time.isoformat(),
        "run_date": ranked_payload.get("run_date"),
        "site_url": SITE_BASE_URL,
        "raw_total": len([item for item in raw_payload.get("items") or [] if isinstance(item, dict)]),
        "ranked_total": ranked_total,
        "topic_counts": topic_counts,
        "window_counts": window_counts,
        "query_error_count": len(errors),
        "query_errors": errors[:8],
        "source_radar_ok_count": radar_ok,
        "source_radar_failed_count": radar_failed,
        "static_output_count": static_outputs.get("count"),
        "static_retained_old_details": static_outputs.get("retained_old_details", 0),
        "detail_retention_days": static_outputs.get("detail_retention_days", detail_retention_days()),
        "daily_brief_exists": (output_dir / "latest_daily_brief.json").exists(),
        "manifest_exists": (output_dir / "latest_hotspots_manifest.json").exists(),
        "llm_editorial": {
            "enabled": bool(llm_status.get("enabled")),
            "live_enabled": bool(llm_status.get("live_enabled", llm_status.get("enabled"))),
            "model": llm_status.get("model") or "",
            "applied": int(llm_status.get("applied") or 0),
            "errors": llm_errors,
            "degraded_reason": llm_degraded_reason,
        },
        "sitemap_url": page_url("sitemap.xml"),
        "ai_context_url": page_url("ai-context.txt"),
        "warnings": warnings,
    }


def write_health_payload(
    output_dir: Path,
    raw_payload: dict[str, object],
    ranked_payload: dict[str, object],
    windows_payload: dict[str, object],
    query_stats: list[dict[str, object]],
    source_radar_payload: dict[str, object] | None,
    static_outputs: dict[str, object],
    reference_time: datetime,
) -> Path:
    path = output_dir / "health.json"
    write_json(
        path,
        build_health_payload(
            output_dir,
            raw_payload,
            ranked_payload,
            windows_payload,
            query_stats,
            source_radar_payload,
            static_outputs,
            reference_time,
        ),
    )
    return path


def detail_retention_days() -> int:
    raw = os.environ.get("HOTSPOT_DETAIL_RETENTION_DAYS", str(DETAIL_RETENTION_DAYS_DEFAULT))
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return DETAIL_RETENTION_DAYS_DEFAULT


def old_detail_title(path: Path) -> str:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")[:32768]
    except OSError:
        return ""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = HTML_TAG_RE.sub("", match.group(1))
    title = unescape(title)
    title = re.sub(r"\s*\|\s*RDXW\s*热点详情\s*$", "", title).strip()
    return title


def should_prune_old_detail(path: Path, reference_time: datetime) -> bool:
    old_title = old_detail_title(path)
    if old_title and low_value_item_title(path.parent.name, old_title):
        return True
    retention_days = detail_retention_days()
    if retention_days <= 0:
        return True
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=reference_time.tzinfo)
    except OSError:
        return True
    return (reference_time - mtime).total_seconds() > retention_days * 24 * 3600


def ensure_noindex_html(path: Path) -> bool:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    if 'name="robots" content="noindex,follow"' in html:
        return False
    meta = '<meta name="robots" content="noindex,follow" />'
    if re.search(r'<meta\s+name="robots"\s+content="[^"]*"\s*/?>', html, re.IGNORECASE):
        new_html = re.sub(
            r'<meta\s+name="robots"\s+content="[^"]*"\s*/?>',
            meta,
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        new_html = html.replace("</head>", f"  {meta}\n</head>", 1)
    if new_html != html:
        path.write_text(new_html, encoding="utf-8")
        return True
    return False


def collect_detail_items(ranked_payload: dict[str, object], windows_payload: dict[str, object]) -> list[dict[str, object]]:
    collected: dict[str, dict[str, object]] = {}
    for raw in ranked_payload.get("items") or []:
        if isinstance(raw, dict):
            item = enrich_item_for_publication(raw)
            item["search_index_candidate"] = True
            collected[str(item["detail_path"])] = item
    windows = windows_payload.get("windows") if isinstance(windows_payload, dict) else {}
    if isinstance(windows, dict):
        for window in windows.values():
            if not isinstance(window, dict):
                continue
            for raw in window.get("items") or []:
                if isinstance(raw, dict):
                    item = enrich_item_for_publication(raw)
                    detail_path = str(item["detail_path"])
                    if detail_path in collected:
                        existing = collected[detail_path]
                        for key, value in item.items():
                            if existing.get(key) in (None, "", [], {}):
                                existing[key] = value
                        continue
                    item["search_index_candidate"] = False
                    collected[detail_path] = item
    return list(collected.values())


def write_static_site_outputs(output_dir: Path, ranked_payload: dict[str, object], windows_payload: dict[str, object], manifest: dict[str, object]) -> dict[str, object]:
    site_root = output_dir.parent if output_dir.name == "output" else output_dir
    generated_dt = parse_ranked_timestamp(ranked_payload.get("reference_time")) or datetime.now().astimezone()
    lastmod = generated_dt.date().isoformat()
    written: list[str] = []
    indexnow_key = ensure_indexnow_key_file(site_root)
    written.append(INDEXNOW_KEY_FILE)
    topic_payloads: dict[tuple[str, str], dict[str, object]] = {}
    core_sitemap_urls: list[tuple[str, str]] = [
        (page_url(""), lastmod),
        (page_url("creator-topics.html"), lastmod),
        (page_url("today-sports-hotspots.html"), lastmod),
        (page_url("esports-hotspot-daily.html"), lastmod),
        (page_url("ai-hotspot-tracker.html"), lastmod),
        (page_url("weekly/index.html"), lastmod),
        (page_url("methodology.html"), lastmod),
        (page_url("api.html"), lastmod),
        (page_url("about.html"), lastmod),
        (page_url("privacy.html"), lastmod),
        (page_url("terms.html"), lastmod),
        (page_url("contact.html"), lastmod),
    ]
    topic_sitemap_urls: list[tuple[str, str]] = []
    daily_sitemap_urls: list[tuple[str, str]] = []
    hot_sitemap_urls: list[tuple[str, str]] = []

    for spec in WINDOW_SPECS:
        window_key = spec["key"]
        for topic in ALL_TOPICS:
            payload_path = output_dir / "topics" / f"{window_key}_{topic}.json"
            if not payload_path.exists():
                continue
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                topic_payloads[(window_key, topic)] = payload
            page_name = topic_page_name(topic, window_key)
            page_path = site_root / page_name
            page_path.write_text(render_topic_static_page(payload, page_name), encoding="utf-8")
            written.append(page_name)
            core_sitemap_urls.append((page_url(page_name), lastmod))

    detail_items = collect_detail_items(ranked_payload, windows_payload)
    current_detail_paths = {str(item.get("detail_path") or "") for item in detail_items if item.get("detail_path")}
    removed: list[str] = []
    retained_old = 0
    noindexed_retained_old = 0
    hot_root = site_root / "hot"
    if hot_root.exists():
        for old_path in hot_root.glob("*/*.html"):
            rel = old_path.relative_to(site_root).as_posix()
            if rel in current_detail_paths:
                continue
            if not should_prune_old_detail(old_path, generated_dt):
                if ensure_noindex_html(old_path):
                    noindexed_retained_old += 1
                retained_old += 1
                continue
            try:
                old_path.unlink()
                removed.append(rel)
            except OSError:
                pass
    for item in detail_items:
        detail_path = str(item.get("detail_path") or "")
        if not detail_path:
            continue
        page_path = site_root / detail_path
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(render_hotspot_detail_page(item), encoding="utf-8")
        written.append(detail_path)
        if detail_is_search_indexable(item):
            hot_sitemap_urls.append((page_url(detail_path), lastmod))

    daily_dir = site_root / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_name = f"daily/{ranked_payload.get('run_date')}.html"
    (site_root / daily_name).write_text(render_daily_static_page(ranked_payload), encoding="utf-8")
    written.append(daily_name)
    refreshed_daily_meta = refresh_daily_archive_meta(site_root)
    daily_sitemap_urls = daily_archive_sitemap_urls(site_root, lastmod)

    cluster_pages = build_seo_cluster_pages(ranked_payload, windows_payload)
    if cluster_pages:
        cluster_root = site_root / "topics"
        cluster_root.mkdir(parents=True, exist_ok=True)
        for page in cluster_pages:
            path = str(page.get("path") or "")
            if not path:
                continue
            (site_root / path).parent.mkdir(parents=True, exist_ok=True)
            (site_root / path).write_text(str(page.get("html") or ""), encoding="utf-8")
            written.append(path)
            topic_sitemap_urls.append((page_url(path), lastmod))
        index_path = "topics/index.html"
        (site_root / index_path).write_text(render_seo_cluster_index(cluster_pages, str(ranked_payload.get("run_date") or "")), encoding="utf-8")
        written.append(index_path)
        topic_sitemap_urls.append((page_url(index_path), lastmod))

    (site_root / "index.html").write_text(render_home_static_page(ranked_payload, topic_payloads, ""), encoding="utf-8")
    (site_root / "home.html").write_text(render_home_static_page(ranked_payload, topic_payloads, ""), encoding="utf-8")
    (site_root / "creator-topics.html").write_text(render_creator_landing_page(ranked_payload, topic_payloads), encoding="utf-8")
    written.extend(["index.html", "home.html", "creator-topics.html"])
    for spec in stable_landing_specs():
        path = str(spec.get("path") or "")
        topic = str(spec.get("topic") or "")
        landing_items = topic_items_from_payloads(ranked_payload, topic_payloads, topic, 12)
        (site_root / path).write_text(render_stable_landing_page(spec, landing_items, str(ranked_payload.get("run_date") or "")), encoding="utf-8")
        written.append(path)
    weekly_dir = site_root / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    weekly_name = weekly_report_page_name(generated_dt)
    weekly_html = render_weekly_report_page(ranked_payload, windows_payload, generated_dt, weekly_name)
    (site_root / weekly_name).write_text(weekly_html, encoding="utf-8")
    (weekly_dir / "index.html").write_text(render_weekly_report_page(ranked_payload, windows_payload, generated_dt, "weekly/index.html"), encoding="utf-8")
    core_sitemap_urls.append((page_url(weekly_name), lastmod))
    written.extend([weekly_name, "weekly/index.html"])
    (site_root / "methodology.html").write_text(render_methodology_page(ranked_payload), encoding="utf-8")
    (site_root / "api.html").write_text(render_api_page(manifest, ranked_payload), encoding="utf-8")
    (site_root / "feedback.html").write_text(render_feedback_page(), encoding="utf-8")
    embed_dir = site_root / "embed"
    embed_dir.mkdir(parents=True, exist_ok=True)
    (embed_dir / "latest.html").write_text(render_embed_latest_page(ranked_payload), encoding="utf-8")
    written.extend(["methodology.html", "api.html", "feedback.html", "embed/latest.html"])
    (site_root / "feed.xml").write_text(render_rss_feed(ranked_payload), encoding="utf-8")
    (site_root / "llms.txt").write_text(render_llms_txt(manifest, ranked_payload), encoding="utf-8")
    (site_root / "ai-context.txt").write_text(render_ai_context_txt(manifest, ranked_payload), encoding="utf-8")
    priority_urls = build_search_console_priority_urls(ranked_payload, cluster_pages, daily_name, weekly_name)
    (site_root / "search-console-priority-urls.txt").write_text(
        "\n".join(row["url"] for row in priority_urls) + "\n",
        encoding="utf-8",
    )
    write_json(output_dir / "search_console_priority_urls.json", {"run_date": ranked_payload.get("run_date"), "items": priority_urls})

    core_sitemap_urls = dedupe_sitemap_urls(core_sitemap_urls)
    topic_sitemap_urls = dedupe_sitemap_urls(topic_sitemap_urls)
    daily_sitemap_urls = dedupe_sitemap_urls(daily_sitemap_urls)
    hot_sitemap_urls = dedupe_sitemap_urls(hot_sitemap_urls)
    all_sitemap_urls = dedupe_sitemap_urls(core_sitemap_urls + topic_sitemap_urls + daily_sitemap_urls + hot_sitemap_urls)
    split_sitemaps = [
        ("sitemap-core.xml", core_sitemap_urls),
        ("sitemap-topics.xml", topic_sitemap_urls),
        ("sitemap-daily.xml", daily_sitemap_urls),
        ("sitemap-hot.xml", hot_sitemap_urls),
    ]
    for sitemap_name, urls in split_sitemaps:
        (site_root / sitemap_name).write_text(render_sitemap(urls), encoding="utf-8")
    sitemap_index_rows = [(page_url(name), lastmod) for name, _urls in split_sitemaps]
    (site_root / "sitemap.xml").write_text(render_sitemap_index(sitemap_index_rows), encoding="utf-8")
    (site_root / "sitemap.txt").write_text(render_sitemap_txt(all_sitemap_urls), encoding="utf-8")
    written.extend([
        "feed.xml",
        "llms.txt",
        "ai-context.txt",
        "search-console-priority-urls.txt",
        "output/search_console_priority_urls.json",
        "sitemap.xml",
        "sitemap-core.xml",
        "sitemap-topics.xml",
        "sitemap-daily.xml",
        "sitemap-hot.xml",
        "sitemap.txt",
    ])
    return {
        "written": written,
        "removed": removed,
        "retained_old_details": retained_old,
        "noindexed_retained_old_details": noindexed_retained_old,
        "detail_retention_days": detail_retention_days(),
        "sitemap_counts": {
            "core": len(core_sitemap_urls),
            "topics": len(topic_sitemap_urls),
            "daily": len(daily_sitemap_urls),
            "hot": len(hot_sitemap_urls),
            "all": len(all_sitemap_urls),
        },
        "indexable_hot_details": len(hot_sitemap_urls),
        "total_current_details": len(detail_items),
        "refreshed_daily_meta": refreshed_daily_meta,
        "indexnow_key_location": page_url(INDEXNOW_KEY_FILE) if indexnow_key else "",
        "count": len(written),
    }


def filter_ranked(items: list[dict[str, object]], top: int, min_score: float, reference_time: datetime) -> list[dict[str, object]]:
    age_windows = [
        {"sports": 48, "esports": 48, "ai": 72, "entertainment": 72, "platform": 96, "github": 24 * 14},
        {"sports": 72, "esports": 72, "ai": 96, "entertainment": 96, "platform": 24 * 7, "github": 24 * 21},
        None,
    ]

    def blocked_item(item: dict[str, object], windows: dict[str, float] | None) -> bool:
        topic = str(item.get("topic") or "sports")
        score = float(item.get("total_score", item.get("score", 0)) or 0)
        if score < min_score:
            return True
        topic_type = str(item.get("topic_type") or "")
        if topic_type.endswith("low_value"):
            return True
        if low_value_item_title(topic, str(item.get("title") or "")):
            return True
        value_score = numeric_score(item.get("editorial_value_score"), 0.0)
        if value_score and value_score < 5.0 and topic in {"platform", "entertainment", "ai"}:
            return True
        source = str(item.get("source") or "").strip().lower()
        if any(flag in source for flag in ("新浪", "手机新浪", "facebook", "腾讯体育社区")):
            return True
        if windows is None:
            return False
        latest_published_at = parse_ranked_timestamp(item.get("latest_published_at"))
        if latest_published_at is None:
            latest_published_at = parse_ranked_timestamp(item.get("published_at"))
        if latest_published_at is None:
            return False
        age_hours = (reference_time - latest_published_at).total_seconds() / 3600
        return age_hours > windows.get(topic, 72)

    for windows in age_windows:
        grouped: dict[str, list[dict[str, object]]] = {}
        for item in items:
            if blocked_item(item, windows):
                continue
            topic = str(item.get("topic") or "sports")
            grouped.setdefault(topic, []).append(item)
        filtered: list[dict[str, object]] = []
        for topic in ALL_TOPICS:
            filtered.extend(grouped.get(topic, [])[:top])
        if filtered:
            minimum_expected = min(top, 8) * max(1, len([topic for topic in grouped if grouped.get(topic)]))
            if len(filtered) >= minimum_expected or windows is None:
                return filtered
    return []


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

    output_dir = Path(args.output_dir)
    sources_dir = Path(args.sources_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    translation_cache_path = Path(args.sources_dir) / "translation_cache.json"
    translation_cache = load_translation_cache(translation_cache_path)
    merged_items = localize_platform_items(merged_items, translation_cache)
    save_translation_cache(translation_cache_path, translation_cache)

    ranked_items = rank_items(merged_items, args.top, reference_time=reference_time)
    ranked_items = enrich_items_for_publication(ranked_items)
    ranked_items = filter_ranked(ranked_items, args.top, args.min_score, reference_time)
    ranked_items = semantic_merge_ranked_items(ranked_items, reference_time, args.top)
    llm_editorial_status = apply_llm_editorial_to_items(ranked_items, reference_time)
    enrich_items_for_publication(ranked_items)

    snapshot_output_dir = output_dir / "snapshots"
    snapshot_sources_dir = sources_dir / "snapshots"
    snapshot_output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_sources_dir.mkdir(parents=True, exist_ok=True)

    raw_path = sources_dir / f"{stamp}_google_news_raw.json"
    ranked_json_path = output_dir / f"{stamp}_hotspots_ranked.json"
    ranked_md_path = output_dir / f"{stamp}_hotspots_ranked.md"
    latest_json_path = output_dir / "latest_hotspots_ranked.json"
    latest_md_path = output_dir / "latest_hotspots_ranked.md"
    windows_json_path = output_dir / "latest_hotspots_windows.json"
    llm_editorial_status_path = output_dir / "llm_editorial_status.json"
    run_stamp = reference_time.strftime("%Y%m%dT%H%M%S")
    raw_snapshot_path = snapshot_sources_dir / f"{run_stamp}_google_news_raw.json"
    ranked_snapshot_path = snapshot_output_dir / f"{run_stamp}_hotspots_ranked.json"
    ranked_snapshot_md_path = snapshot_output_dir / f"{run_stamp}_hotspots_ranked.md"

    raw_payload = {
        "date": stamp,
        "run_date": run_date,
        "reference_time": reference_time.isoformat(),
        "query_stats": query_stats,
        "items": merged_items,
    }

    ranked_payload = {
        "date": stamp,
        "run_date": run_date,
        "reference_time": reference_time.isoformat(),
        "items": ranked_items,
        "topic_counts": dict(Counter(item.get("topic") for item in ranked_items)),
        "topic_labels": {
            "sports": "体育热点",
            "esports": "电竞热点",
            "ai": "AI科技热点",
            "entertainment": "泛娱乐热点",
            "platform": "平台热议",
            "github": "GitHub热点项目",
        },
    }
    write_json(llm_editorial_status_path, llm_editorial_status)
    windows_payload = build_window_payloads(output_dir, ranked_payload, reference_time, args.top)
    manifest_path = write_split_topic_payloads(output_dir, ranked_payload, windows_payload)
    source_radar_path = write_source_radar_payload(output_dir, reference_time, translation_cache)
    try:
        source_radar_payload = json.loads(source_radar_path.read_text(encoding="utf-8"))
    except Exception:
        source_radar_payload = {}
    source_quality_path = write_source_quality_payload(output_dir, ranked_payload, windows_payload, source_radar_payload, reference_time)
    daily_brief_path = write_daily_brief_payload(output_dir, ranked_payload, reference_time, per_section=2)
    save_translation_cache(translation_cache_path, translation_cache)
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest_payload = {}
    static_outputs = write_static_site_outputs(output_dir, ranked_payload, windows_payload, manifest_payload)

    write_json(raw_path, raw_payload)
    write_json(raw_snapshot_path, raw_payload)
    write_json(ranked_json_path, ranked_payload)
    write_text(ranked_md_path, build_markdown(ranked_items, markdown_top=10))
    write_json(ranked_snapshot_path, ranked_payload)
    write_text(ranked_snapshot_md_path, build_markdown(ranked_items, markdown_top=10))
    write_json(latest_json_path, ranked_payload)
    write_text(latest_md_path, build_markdown(ranked_items, markdown_top=10))
    write_json(windows_json_path, compact_window_payload(windows_payload))
    health_path = write_health_payload(
        output_dir,
        raw_payload,
        ranked_payload,
        windows_payload,
        query_stats,
        source_radar_payload,
        static_outputs,
        reference_time,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "raw_total": len(merged_items),
                "ranked_total": len(ranked_items),
                "query_stats": query_stats,
                "raw": str(raw_path),
                "raw_snapshot": str(raw_snapshot_path),
                "ranked_json": str(ranked_json_path),
                "ranked_md": str(ranked_md_path),
                "ranked_snapshot_json": str(ranked_snapshot_path),
                "ranked_snapshot_md": str(ranked_snapshot_md_path),
                "latest_json": str(latest_json_path),
                "latest_md": str(latest_md_path),
                "windows_json": str(windows_json_path),
                "llm_editorial_status_json": str(llm_editorial_status_path),
                "manifest_json": str(manifest_path),
                "source_radar_json": str(source_radar_path),
                "source_quality_json": str(source_quality_path),
                "daily_brief_json": str(daily_brief_path),
                "health_json": str(health_path),
                "static_outputs": static_outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
