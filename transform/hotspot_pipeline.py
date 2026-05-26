#!/usr/bin/env python3
# Hotspot ranking pipeline for sports / ai / entertainment.

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

TOPIC_LABELS = {
    "sports": "体育热点",
    "esports": "电竞热点",
    "ai": "AI科技热点",
    "entertainment": "泛娱乐热点",
    "platform": "平台热议",
    "github": "GitHub热点项目",
}
TOPIC_ORDER = ["sports", "esports", "ai", "entertainment", "platform", "github"]
RAW_PLATFORM_TOPICS = {"x", "youtube"}

SPORTS_WORDS = [
    "英超", "NBA", "欧冠", "中超", "意甲", "德甲", "法甲", "亚冠", "梅西", "C罗",
    "球队", "比赛", "晋级", "进球", "比分", "主场", "客场", "女篮", "男篮",
    "WTT", "斯诺克", "WCBA", "勇士", "太阳", "湖人", "曼联", "曼城", "国米",
    "Inter", "Milan", "Warriors", "Rockets", "Mbappe", "Liverpool", "Serie A",
]
ESPORTS_WORDS = [
    "电竞", "电子竞技", "英雄联盟", "LPL", "LCK", "LCS", "KPL", "王者荣耀", "和平精英",
    "CS2", "CSGO", "DOTA2", "Dota2", "VALORANT", "无畏契约", "穿越火线", "MSI", "S赛",
    "世界赛", "季中冠军赛", "总决赛", "战队", "俱乐部", "选手", "职业联赛", "电竞赛事",
    "Faker", "Uzi", "TheShy", "Rookie", "Chovy", "JDG", "BLG", "TES", "WBG", "IG",
]
AI_WORDS = [
    "OpenAI", "ChatGPT", "Gemini", "Sora", "Claude", "英伟达", "苹果AI", "模型",
    "人工智能", "大模型", "推理", "智能体", "NVIDIA", "Google AI", "Agent",
]
ENT_WORDS = [
    "微博热搜", "电影", "电视剧", "综艺", "明星", "演员", "导演", "票房",
    "热搜", "定档", "上映", "回应争议", "娱乐",
]
X_WORDS = [
    "x.com", "twitter.com", "twitter", "tweet", "tweets", "posted on x",
    "x post", "thread", "发文", "帖文",
]
YOUTUBE_WORDS = [
    "youtube", "youtu.be", "shorts", "trailer", "teaser", "podcast",
    "interview", "livestream", "youtube video", "视频",
]

SPORTS_HIGH_VALUE_SOURCES = ["懂球帝", "直播吧", "体坛周报", "虎扑", "ESPN", "Sky Sports", "The Athletic", "Reuters", "AP"]
ESPORTS_HIGH_VALUE_SOURCES = ["5EPlay", "ScoreGG", "玩加电竞", "兔玩", "新浪电竞", "Max+", "Reuters", "AP"]
SPORTS_LOW_VALUE_PATTERNS = ["集锦", "录像", "回放", "直播安排", "赛程表", "节目表", "官方网站", "官方平台", "官方入口", "比赛中心", "文字实录", "图文直播", "即时比分"]
ESPORTS_LOW_VALUE_PATTERNS = ["直播安排", "赛程表", "节目表", "集锦", "回放", "录像", "看点预告", "官方网站", "官方平台", "官方入口", "图文直播", "即时比分"]
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
AI_GOV_TRAINING_LOW = [
    "省属企业", "通识培训", "培训课程", "应用场景", "产业园", "示范区", "数字员工", "生态大会",
    "十周年", "赋能", "新范式", "联盟倡议", "试点", "tour", "上海站", "APEC", "女性友好",
    "国家档案局", "司法应用指南", "食品产业", "产业发展与安全", "支持采购大模型", "国务院",
    "政策", "规划", "应用试点", "示范应用", "产业大会", "论坛",
]
AI_BREAKING_LOW = ["早报", "一夜蒸发", "多条新闻混合", "A股", "股价", "市值"]

ENT_LOW_VALUE_PATTERNS = [
    "电影+消费", "消费市场", "市场活力", "经济图景", "集团战略", "产业发展", "多元体验", "新质赋能",
    "演唱会定档", "杏花节", "比亚迪", "充电", "续航", "km", "城市活动", "文旅活动", "消费节", "景区活动",
    "明星台企", "武术明星", "体育明星", "奥运冠军", "冠军家里", "明星大赛",
    "携手", "品牌合作", "代言", "服饰", "启动仪式", "开幕式", "大赛开幕", "活动开幕", "战略合作", "商业合作", "新时代", "产业合作", "文旅", "景区", "消费节",
    "首映式", "电影节", "北影节", "北京国际电影节", "论坛", "圆桌会", "创作营", "启动", "活动",
    "中国电影博物馆", "聚焦太极文化传承", "沪游双周报", "嘉年华", "展映", "影展",
]
ENT_HIGH_VALUE_PATTERNS = ["明星", "回应", "争议", "道歉", "塌房", "热搜", "票房破", "定档", "撤档", "开播", "爆了", "封神", "翻车"]
ENT_TITLE_BONUS_PATTERNS = ["票房", "定档", "上映", "电影节", "撤档", "改档", "开播", "官宣阵容", "主演", "导演", "回应", "争议", "道歉", "塌房", "翻车"]
ENT_STAR_ALLOWED_RE = re.compile(r"(?:演员|艺人|歌手|导演|主持人|爱豆|偶像|男演员|女演员|综艺|电影|电视剧)")
ENT_CONTROVERSY_RE = re.compile(r"(?:翻车|致歉|道歉|回应|终止合作|失责|开除|塌房|争议|被曝|封杀|下架)", re.IGNORECASE)

TITLE_PARTY_PATTERNS = ["终于", "炸了", "塌了", "全网热议", "太敢说", "万万没想到", "惊呆", "杀疯了"]

SOURCE_SUFFIX_RE = re.compile(r"(?:\s*[-—|｜]\s*[^-—|｜]{2,24})+$")
ESPORTS_SOURCE_SUFFIX_RE = re.compile(
    r"\s*[-—]\s*[^-—|｜]{1,24}\s*[-—]\s*(?:Score[-—]?电竞玩家赛事社区|scoregg\.com)\s*$",
    re.IGNORECASE,
)
SPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)

EDITOR_NOTE_BANNED = ["值得关注", "适合关注", "重点看", "可以观察", "临场变化", "核心卖点", "主要卖点", "宣发期", "信息明确", "已经成型"]

BLOCKED_SOURCE_PATTERNS = [
    "新浪",
    "手机新浪",
    "新浪财经",
    "腾讯体育社区",
    "facebook",
]
COMMUNITY_SOURCE_PATTERNS = ["虎扑", "懂球帝", "scoregg", "score-电竞玩家赛事社区"]
HIGH_TRUST_SOURCE_PATTERNS = [
    "央视",
    "新华",
    "人民网",
    "中国新闻网",
    "直播吧",
    "懂球帝",
    "虎扑",
    "5eplay",
    "scoregg",
    "score-电竞玩家赛事社区",
    "it之家",
    "36氪",
    "量子位",
    "机器之心",
    "thepaper",
    "澎湃",
    "github",
    "product hunt",
    "reuters",
    "associated press",
    "espn",
    "the athletic",
    "nba.com",
    "uefa",
]
MEDIUM_TRUST_SOURCE_PATTERNS = ["腾讯", "网易", "搜狐体育", "b站", "哔哩哔哩", "youtube", "x.com", "twitter"]
LOW_TRUST_SOURCE_PATTERNS = ["新浪", "手机新浪", "facebook", "腾讯体育社区", "美通社", "财富号", "车家号"]
SOURCE_SCORE_WEIGHTS = {
    "央视网": 2.0,
    "央视体育": 2.0,
    "新华网": 1.9,
    "人民网": 1.8,
    "中国新闻网": 1.8,
    "腾讯网": 1.7,
    "腾讯体育": 1.8,
    "网易体育": 1.7,
    "搜狐体育": 1.6,
    "懂球帝": 1.4,
    "直播吧": 1.5,
    "虎扑体育": 1.2,
    "虎扑": 1.2,
    "5eplay": 1.6,
    "scoregg.com": 1.3,
    "reuters": 2.0,
    "associated press": 2.0,
    "ap": 2.0,
    "espn": 1.8,
    "the athletic": 1.8,
    "bbc sport": 1.7,
    "sky sports": 1.7,
    "nba.com": 1.7,
    "mlb.com": 1.7,
    "uefa": 1.7,
    "youtube": 1.5,
    "x": 1.1,
    "twitter": 1.1,
    "github": 1.8,
}
STORYLINE_PATTERNS = {
    "transfer": ["transfer", "trade", "sign", "signing", "contract", "loan", "转会", "加盟", "签约", "续约", "离队", "官宣"],
    "injury": ["injury", "injured", "ruled out", "questionable", "doubtful", "returns", "return", "伤病", "伤缺", "伤停", "伤退", "报销", "缺席", "复出", "回归"],
    "controversy": ["ban", "suspension", "scandal", "controversy", "criticism", "争议", "禁赛", "处罚", "罚单", "冲突", "质疑", "回应", "调查"],
    "lineup": ["preview", "lineup", "lineups", "kickoff", "赛前", "前瞻", "对阵", "迎战", "首发", "名单", "抽签", "分档", "名单公布", "今晚", "明日", "出战"],
    "result": ["beat", "beats", "defeat", "defeats", "win", "wins", "won", "loss", "eliminate", "eliminated", "comeback", "clinch", "final", "semifinal", "战胜", "击败", "不敌", "险胜", "大胜", "战平", "力克", "破门", "建功", "救主", "逆转", "绝杀", "晋级", "淘汰", "出局", "无缘", "夺冠", "问鼎", "冠军", "收官"],
    "star": ["scores", "scored", "double-double", "hat-trick", "record", "milestone", "mvp", "砍下", "轰下", "拿到", "三双", "双响", "帽子戏法", "纪录", "里程碑"],
    "business": ["media rights", "broadcast", "sponsorship", "revenue", "ownership", "赞助", "版权", "转播", "收购", "商业", "融资"],
    "official": ["official", "announced", "announcement", "statement", "官宣", "发布", "回应", "公告"],
    "thread": ["thread", "长帖", "长文", "breakdown", "explained", "解析", "拆解"],
    "video": ["video", "视频", "trailer", "预告", "clip", "shorts", "短视频"],
    "live": ["live", "livestream", "stream", "直播", "回放"],
    "reaction": ["reaction", "reacts", "hot take", "热议", "回应", "评论"],
}
STORYLINE_LABELS = {
    "transfer": "转会",
    "injury": "伤病",
    "controversy": "争议",
    "lineup": "赛前",
    "result": "赛果",
    "star": "球星",
    "business": "商业",
    "official": "官方",
    "thread": "长帖",
    "video": "视频",
    "live": "直播",
    "reaction": "解读",
}
KEYWORD_RULES = [
    {"label": "季后赛", "weight": 1.7, "patterns": ["季后赛", "playoff", "playoffs"]},
    {"label": "附加赛", "weight": 1.6, "patterns": ["附加赛", "play-in"]},
    {"label": "决赛", "weight": 1.6, "patterns": ["决赛", "final"]},
    {"label": "半决赛", "weight": 1.5, "patterns": ["半决赛", "semifinal"]},
    {"label": "夺冠", "weight": 1.6, "patterns": ["夺冠", "冠军", "问鼎", "卫冕"]},
    {"label": "绝杀", "weight": 1.7, "patterns": ["绝杀", "buzzer-beater"]},
    {"label": "逆转", "weight": 1.4, "patterns": ["逆转", "comeback", "翻盘"]},
    {"label": "晋级", "weight": 1.8, "patterns": ["晋级", "advance", "advanced"]},
    {"label": "淘汰", "weight": 1.8, "patterns": ["淘汰", "eliminate", "eliminated"]},
    {"label": "出局", "weight": 1.6, "patterns": ["出局", "无缘"]},
    {"label": "伤病", "weight": 1.5, "patterns": ["伤病", "伤缺", "伤退", "injury"]},
    {"label": "复出", "weight": 1.3, "patterns": ["复出", "回归", "returns", "return"]},
    {"label": "转会", "weight": 1.5, "patterns": ["转会", "加盟", "签约", "trade", "transfer"]},
    {"label": "官宣", "weight": 1.3, "patterns": ["官宣", "official"]},
    {"label": "争议", "weight": 1.4, "patterns": ["争议", "禁赛", "处罚", "controversy", "suspension"]},
    {"label": "纪录", "weight": 1.2, "patterns": ["纪录", "record", "里程碑", "milestone"]},
    {"label": "国足", "weight": 1.3, "patterns": ["国足"]},
    {"label": "中超", "weight": 1.2, "patterns": ["中超"]},
    {"label": "CBA", "weight": 1.3, "patterns": ["cba"]},
    {"label": "NBA", "weight": 1.3, "patterns": ["nba"]},
    {"label": "中国女篮", "weight": 1.5, "patterns": ["中国女篮", "女篮世界杯"]},
    {"label": "中国球员", "weight": 1.4, "patterns": ["中国球员", "中国选手"]},
    {"label": "WTT", "weight": 1.4, "patterns": ["wtt", "太原站"]},
    {"label": "斯诺克", "weight": 1.3, "patterns": ["斯诺克"]},
    {"label": "MSI", "weight": 1.4, "patterns": ["msi"]},
    {"label": "世界赛", "weight": 1.4, "patterns": ["世界赛", "s赛"]},
    {"label": "智能体", "weight": 1.4, "patterns": ["智能体", "agent"]},
    {"label": "开源", "weight": 1.2, "patterns": ["开源", "open-source", "opensource"]},
    {"label": "模型更新", "weight": 1.3, "patterns": ["模型更新", "model", "gpt", "gemini", "claude", "sora"]},
    {"label": "定档", "weight": 1.3, "patterns": ["定档", "上映", "开播"]},
    {"label": "票房", "weight": 1.2, "patterns": ["票房"]},
    {"label": "热搜", "weight": 1.1, "patterns": ["热搜"]},
    {"label": "X热议", "weight": 1.0, "patterns": ["x.com", "twitter.com", "tweet", "thread", "发文"]},
    {"label": "YouTube", "weight": 1.0, "patterns": ["youtube", "youtu.be"]},
    {"label": "直播", "weight": 1.1, "patterns": ["live", "livestream", "直播"]},
    {"label": "Shorts", "weight": 1.0, "patterns": ["shorts", "短视频"]},
    {"label": "访谈", "weight": 1.1, "patterns": ["interview", "podcast", "访谈", "采访"]},
    {"label": "预告", "weight": 1.0, "patterns": ["trailer", "teaser", "预告"]},
]
KEYWORD_WEIGHTS = {rule["label"]: rule["weight"] for rule in KEYWORD_RULES}
LEAGUE_KEYWORDS = {
    "NBA": ["nba", "勇士", "湖人", "火箭", "凯尔特人", "雷霆", "太阳", "尼克斯", "掘金", "黄蜂", "魔术", "快船"],
    "CBA": ["cba", "辽宁男篮", "广东男篮", "北京男篮", "浙江男篮", "广厦", "上海久事", "北控", "山东"],
    "WCBA": ["wcba", "山西女篮", "四川女篮", "中国女篮"],
    "中超": ["中超", "泰山", "海港", "津门虎", "海牛", "成都蓉城", "北京国安", "韦世豪", "廖力生"],
    "中国女篮": ["中国女篮", "女篮世界杯"],
    "国乒": ["国乒", "wtt", "王楚钦", "孙颖莎", "樊振东", "黄友政", "石洵瑶", "太原站"],
    "国羽": ["羽毛球", "国羽", "陈雨菲", "石宇奇"],
    "网球": ["网球", "atp", "wta", "郑钦文", "张帅", "德约科维奇", "阿尔卡拉斯", "斯图加特", "法网"],
    "斯诺克": ["斯诺克", "周跃龙", "庞俊旭", "丁俊晖", "赵心童"],
    "LPL": ["lpl", "blg", "tes", "wbg", "ig", "jdg"],
    "KPL": ["kpl", "王者荣耀"],
}
ENTITY_PATTERNS = {
    "勇士": ["勇士", "warriors"],
    "湖人": ["湖人", "lakers"],
    "火箭": ["火箭", "rockets"],
    "凯尔特人": ["凯尔特人", "celtics"],
    "太阳": ["太阳", "suns"],
    "雷霆": ["雷霆", "thunder"],
    "尼克斯": ["尼克斯", "knicks"],
    "快船": ["快船", "clippers"],
    "魔术": ["魔术", "magic"],
    "黄蜂": ["黄蜂", "hornets"],
    "詹姆斯": ["詹姆斯", "lebron james"],
    "库里": ["库里", "stephen curry"],
    "东契奇": ["东契奇", "luka doncic"],
    "约基奇": ["约基奇", "nikola jokic"],
    "国足": ["国足"],
    "利物浦": ["利物浦", "liverpool"],
    "拜仁": ["拜仁", "bayern"],
    "阿森纳": ["阿森纳", "arsenal"],
    "皇马": ["皇马", "皇家马德里", "real madrid"],
    "巴萨": ["巴萨", "巴塞罗那", "barcelona"],
    "姆巴佩": ["姆巴佩", "mbappe"],
    "王楚钦": ["王楚钦"],
    "孙颖莎": ["孙颖莎"],
    "郑钦文": ["郑钦文"],
    "张帅": ["张帅"],
    "陈雨菲": ["陈雨菲"],
    "中国女篮": ["中国女篮"],
    "山西女篮": ["山西女篮"],
    "四川女篮": ["四川女篮"],
    "成都蓉城": ["成都蓉城"],
    "北京国安": ["北京国安"],
    "山东泰山": ["山东泰山", "泰山"],
    "上海海港": ["上海海港", "海港"],
    "天津津门虎": ["津门虎"],
    "青岛海牛": ["海牛"],
    "赵继伟": ["赵继伟"],
    "王哲林": ["王哲林"],
    "高诗岩": ["高诗岩"],
    "韦世豪": ["韦世豪"],
    "廖力生": ["廖力生"],
    "黄友政": ["黄友政"],
    "石洵瑶": ["石洵瑶"],
    "周跃龙": ["周跃龙"],
    "庞俊旭": ["庞俊旭"],
    "丁俊晖": ["丁俊晖"],
    "赵心童": ["赵心童"],
    "BLG": ["blg"],
    "WBG": ["wbg"],
    "IG": ["ig"],
}
DOMESTIC_PRIORITY_PATTERNS = [
    "中国", "中国女篮", "中国男篮", "中国球员", "中国选手", "国足", "国乒", "国羽", "中超",
    "足协杯", "CBA", "WCBA", "WTT", "太原站", "斯诺克", "郑钦文", "张帅", "丁俊晖",
    "赵继伟", "韦世豪", "周跃龙", "庞俊旭",
]
DOMESTIC_PRIORITY_LEAGUES = {"CBA", "WCBA", "中超", "中国女篮", "国乒", "国羽", "斯诺克"}
DOMESTIC_PRIORITY_ENTITIES = {
    "中国女篮", "山西女篮", "四川女篮", "成都蓉城", "北京国安", "山东泰山", "上海海港",
    "天津津门虎", "青岛海牛", "赵继伟", "王哲林", "高诗岩", "韦世豪", "廖力生", "黄友政",
    "石洵瑶", "周跃龙", "庞俊旭", "丁俊晖", "赵心童", "王楚钦", "孙颖莎", "郑钦文", "张帅", "陈雨菲",
}
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_BREAK_RE = re.compile(r"<\s*(?:br|/p|/div|/li)\s*/?>", re.IGNORECASE)
PARENS_TRAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")
SELF_PROMO_PATTERNS = [
    "my startup",
    "i built",
    "we built",
    "follow for more",
    "link in bio",
    "subscribe",
    "waitlist",
    "join my",
    "growth hack",
    "newsletter",
    "course",
    "模板下载",
    "私信领取",
    "关注我",
    "点我主页",
    "体验链接",
    "立即试用",
    "保姆级",
    "全自动",
    "彻底取代",
    "都在用",
    "订阅登录",
    "工作流教程",
    "专项优化",
    "让你学会",
]
PLATFORM_LOW_VALUE_PATTERNS = [
    "watch live",
    "where to watch",
    "full stream",
    "full match",
    "观看直播",
    "完整回放",
    "点击观看",
    "链接在此",
    "教程合集",
    "领资料",
    "彻底沦为过去式",
    "一键搞定",
    "秒会",
    "速成",
    "太离谱",
    "直接傻眼",
    "看完直接傻眼",
    "Multi Sub",
    "CCTV电视剧",
    "iQIYI",
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
    "FULL《",
    "经典武侠动作港片",
    "Chinese Film",
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
SPAM_TITLE_RE = re.compile(
    r"results\s+(?:for|on)\b|posts?\s*(?:&|and)\s*updates?|IM电竞|体育博彩|百家乐|送彩金|注册送|投注平台|开户注册|现金网|真人娱乐|"
    r"\b(?:\d{2,8}|[a-z0-9-]{2,})\.(?:vip|tw|top|bet|win|casino)\b",
    re.IGNORECASE,
)
SITE_ROOT = Path(__file__).resolve().parent.parent
EDITORIAL_OVERRIDE_PATH = SITE_ROOT / "config" / "editorial_overrides.json"


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-json", required=False)
    ap.add_argument("--output-markdown", required=False)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--reference-time", required=False)
    return ap.parse_args()


def canonical_topic(topic):
    return "platform" if topic in RAW_PLATFORM_TOPICS else topic


def platform_source_label(source_topic):
    return {"x": "X", "youtube": "YouTube"}.get(str(source_topic or "").lower(), "")


def strip_html(text):
    text = unescape(str(text or ""))
    text = HTML_BREAK_RE.sub("。", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    return SPACE_RE.sub(" ", text).strip()


def dedupe_sentence(text, title="", source=""):
    cleaned = strip_html(text)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    title_norm = normalize_title(title)
    if title_norm and normalize_title(cleaned) == title_norm:
        return ""
    if title and cleaned.startswith(title):
        cleaned = cleaned[len(title):].strip(" -|｜。:：")
    if source:
        cleaned = re.sub(rf"(?:^|\s){re.escape(source)}(?:$|\s)", " ", cleaned, flags=re.IGNORECASE).strip()
    cleaned = SPACE_RE.sub(" ", cleaned).strip(" -|｜。:：")
    return cleaned


def clean_title_text(text):
    cleaned = strip_html(text)
    cleaned = PARENS_TRAIL_RE.sub("", cleaned).strip()
    cleaned = ESPORTS_SOURCE_SUFFIX_RE.sub("", cleaned)
    cleaned = re.sub(
        r"\s*[-—]\s*(?:Score[-—]?电竞玩家赛事社区|scoregg\.com|遥远的布莱梅|木质烧杯)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    cleaned = cleaned.strip(" -|｜")
    return cleaned


def clean_summary_text(text, title="", source=""):
    cleaned = dedupe_sentence(text, title=title, source=source)
    if len(cleaned) > 220:
        cleaned = cleaned[:220].rstrip("，,。 ") + "。"
    return cleaned


@lru_cache(maxsize=1)
def load_editorial_overrides():
    path = Path(os.environ.get("HOTSPOT_EDITORIAL_PATH", str(EDITORIAL_OVERRIDE_PATH)))
    if not path.exists():
        return {"rules": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"rules": []}
    if not isinstance(payload, dict):
        return {"rules": []}
    rules = payload.get("rules")
    if not isinstance(rules, list):
        rules = []
    return {"rules": rules}


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


def normalize_sources(item, title, source, url):
    rows = []
    raw_sources = item.get("sources")
    if isinstance(raw_sources, list):
        for raw in raw_sources:
            if not isinstance(raw, dict):
                continue
            source_name = str(raw.get("source") or raw.get("name") or source or "").strip()
            source_url = str(raw.get("url") or url or "").strip()
            source_title = str(raw.get("title") or title or "").strip()
            rows.append(
                {
                    "source": source_name,
                    "title": source_title,
                    "url": source_url,
                    "domain": domain(source_url),
                }
            )
    if not rows and (source or url):
        rows.append(
            {
                "source": source.strip(),
                "title": title.strip(),
                "url": url.strip(),
                "domain": domain(url.strip()),
            }
        )
    return rows


def normalize_item(item):
    title = clean_title_text(pick(item, "title", "headline", "name"))
    translated_title = clean_title_text(pick(item, "translated_title", default=title))
    original_title = clean_title_text(pick(item, "original_title", default=title))
    source = pick(item, "source", "publisher", "site", "source_name")
    url = pick(item, "url", "link")
    source_url = pick(item, "source_url", "sourceUrl", "source_home_url")
    published_at = pick(item, "published_at", "published", "pubDate", "date", "time")
    latest_published_at = pick(item, "latest_published_at", "latestPublishedAt", default=published_at)
    created_at = pick(item, "created_at", "createdAt", default=published_at)
    raw_topic = str(item.get("source_topic") or item.get("topic") or "")
    keywords = item.get("keywords") or item.get("keywords_hit") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    stars = item.get("stars") or 0
    forks = item.get("forks") or 0
    language = item.get("language")
    repo = item.get("repo") or ""
    summary = clean_summary_text(item.get("summary") or item.get("description") or "", title=title, source=source)
    translated_summary = clean_summary_text(pick(item, "translated_summary", default=summary), title=translated_title or title, source=source)
    original_summary = clean_summary_text(pick(item, "original_summary", default=summary), title=original_title or title, source=source)
    sources = normalize_sources(item, title, source, source_url or url)
    return {
        "title": title.strip(),
        "display_title": translated_title.strip() or title.strip(),
        "original_title": original_title.strip() or title.strip(),
        "source": source.strip(),
        "url": url.strip(),
        "source_url": source_url.strip(),
        "published_at": published_at,
        "latest_published_at": latest_published_at,
        "created_at": created_at,
        "topic": raw_topic,
        "keywords": keywords,
        "stars": stars,
        "forks": forks,
        "language": language,
        "repo": repo,
        "summary": summary,
        "display_summary": translated_summary.strip() or summary,
        "original_summary": original_summary.strip() or summary,
        "sources": sources,
        "source_topic": raw_topic,
        "raw": item,
        "raw_items": [item],
    }


def contains_any(text, words):
    lower = text.lower()
    return any(w.lower() in lower for w in words)


def contains_pattern(text, pattern):
    return pattern.lower() in text.lower()


def normalize_source_name(source):
    return str(source or "").strip().lower()


def is_blocked_source(source):
    lowered = normalize_source_name(source)
    return any(pattern.lower() in lowered for pattern in BLOCKED_SOURCE_PATTERNS)


def is_spam_title(title):
    text = str(title or "").strip()
    if not text:
        return False
    compact = SPACE_RE.sub("", text)
    return bool(SPAM_TITLE_RE.search(text) or SPAM_TITLE_RE.search(compact))


def platform_title_has_keep_signal(title):
    return bool(PLATFORM_KEEP_SIGNAL_RE.search(str(title or "")))


def platform_video_noise_title(title):
    text = str(title or "")
    if not text.strip():
        return False
    if not PLATFORM_VIDEO_NOISE_RE.search(text):
        return False
    return not platform_title_has_keep_signal(text)


def infer_topic(item):
    topic = item.get("topic")
    if topic in TOPIC_LABELS or topic in RAW_PLATFORM_TOPICS:
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
    if contains_any(text, X_WORDS):
        return "x"
    if contains_any(text, YOUTUBE_WORDS):
        return "youtube"
    if contains_any(text, ESPORTS_WORDS):
        return "esports"
    if contains_any(text, AI_WORDS):
        return "ai"
    if contains_any(text, ENT_WORDS):
        return "entertainment"
    if contains_any(text, SPORTS_WORDS):
        return "sports"
    return "sports"


def infer_sports_type(title):
    t = title.lower()
    if contains_any(title, SPORTS_LOW_VALUE_PATTERNS):
        return "sports_low_value"
    if any(k.lower() in t for k in ["injury", "伤", "受伤", "复出", "leaves training", "提前离场"]):
        return "sports_injury"
    if any(k.lower() in t for k in ["refereeing", "争议", "处罚", "禁赛", "调查", "审查", "coach blast"]):
        return "sports_controversy"
    if any(k.lower() in t for k in ["transfer", "sign", "open talks", "转会", "签约", "报价", "合同", "谈判"]):
        return "sports_transfer"
    if re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, SPORTS_RESULT_STRICT):
        return "sports_result"
    if contains_any(title, SPORTS_PREVIEW_FORCE):
        if not (re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, SPORTS_RESULT_EXPLICIT) or contains_any(title, ["赛后"])):
            return "sports_preview"
    if contains_any(title, ["lineups", "赛前", "名单", "抽签", "分档", "前瞻", "预测", "vs", "VS", "天王山"]):
        return "sports_preview"
    if contains_any(title, ["梅西", "C罗", "Mbappe", "Ohtani", "球星", "郑钦文", "张帅", "丁俊晖", "赵心童", "王楚钦", "孙颖莎"]):
        return "sports_star"
    return "sports_low_value"


def infer_esports_type(title):
    t = title.lower()
    if contains_any(title, ["前瞻", "赛前", "对阵", "vs", "VS", "名单", "首发", "预测", "看点"]):
        if not (re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, ["战报", "晋级", "出局", "夺冠", "卫冕", "横扫", "翻盘"])):
            return "esports_preview"
    if re.search(r"\d+\s*[-:比]\s*\d+", title) or contains_any(title, ["战报", "晋级", "出局", "夺冠", "卫冕", "横扫", "翻盘", "让二追三", "击败"]):
        return "esports_result"
    if any(k in t for k in ["transfer", "转会", "签约", "续约", "解约", "合同", "席位", "版权", "赞助", "联赛", "商业"]):
        return "esports_business"
    if any(k in t for k in ["争议", "处罚", "禁赛", "举报", "道歉", "爆料", "冲突", "翻车"]):
        return "esports_controversy"
    if contains_any(title, ["Faker", "Uzi", "TheShy", "Rookie", "Chovy", "Knight", "JackeyLove", "Scout", "Meiko"]):
        return "esports_star"
    if contains_any(title, ESPORTS_LOW_VALUE_PATTERNS):
        return "esports_low_value"
    return "esports_hotsearch"


def infer_ai_type(title):
    if (
        contains_any(title, AI_LOW_VALUE_PATTERNS)
        or contains_any(title, AI_GOV_TRAINING_LOW)
        or contains_any(title, AI_BREAKING_LOW)
    ):
        return "ai_low_value"
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


def infer_x_type(item):
    text = full_text(item)
    compact_title = re.sub(r"\s+", "", str(item.get("title") or ""))
    if (
        is_spam_title(text)
        or is_spam_title(item.get("title"))
        or contains_any(text, SELF_PROMO_PATTERNS)
        or contains_any(text, PLATFORM_LOW_VALUE_PATTERNS)
        or platform_video_noise_title(text)
        or contains_any(str(item.get("title") or ""), TITLE_PARTY_PATTERNS)
        or len(compact_title) > 72
        or str(item.get("title") or "").count("！") + str(item.get("title") or "").count("!") >= 2
    ):
        return "x_low_value"
    if contains_any(text, ["official", "announcement", "announced", "statement", "官宣", "发布", "回应", "公告"]):
        return "x_official"
    if contains_any(text, ["thread", "长帖", "长文", "breakdown", "explained", "拆解", "解析"]):
        return "x_thread"
    if contains_any(text, ["reaction", "reacts", "hot take", "controversy", "热议", "评论", "争议"]):
        return "x_reaction"
    return "x_post"


def infer_youtube_type(item):
    text = full_text(item)
    compact_title = re.sub(r"\s+", "", str(item.get("title") or ""))
    if (
        is_spam_title(text)
        or is_spam_title(item.get("title"))
        or contains_any(text, SELF_PROMO_PATTERNS)
        or contains_any(text, PLATFORM_LOW_VALUE_PATTERNS)
        or platform_video_noise_title(text)
        or contains_any(str(item.get("title") or ""), TITLE_PARTY_PATTERNS)
        or len(compact_title) > 72
        or str(item.get("title") or "").count("！") + str(item.get("title") or "").count("!") >= 2
    ):
        return "youtube_low_value"
    if contains_any(text, ["shorts", "short", "短视频"]):
        return "youtube_short"
    if contains_any(text, ["live", "livestream", "stream", "直播", "回放"]):
        return "youtube_live"
    if contains_any(text, ["trailer", "teaser", "预告", "片段"]):
        return "youtube_trailer"
    if contains_any(text, ["interview", "podcast", "breakdown", "explained", "访谈", "采访", "解析", "解说"]):
        return "youtube_interview"
    return "youtube_video"


def infer_topic_type(topic, item):
    title = item.get("title", "")
    source_topic = str(item.get("source_topic") or "")
    if topic == "ai":
        return infer_ai_type(title)
    if topic == "esports":
        return infer_esports_type(title)
    if topic == "entertainment":
        return infer_ent_type(title)
    if topic == "platform" and source_topic == "x":
        return infer_x_type(item)
    if topic == "platform" and source_topic == "youtube":
        return infer_youtube_type(item)
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


def summary_hint(topic, topic_type, title):
    if topic == "sports":
        return sports_summary_hint(topic_type, title)
    if topic == "esports":
        if topic_type == "esports_preview":
            if contains_any(title, ["vs", "VS", "对阵"]):
                return "对局关注度集中在对线和版本适配。"
            return "赛前信息更适合看阵容和版本方向。"
        if topic_type == "esports_result":
            if contains_any(title, ["晋级", "夺冠", "卫冕", "翻盘", "横扫"]):
                return "结果已经落地，赛果会直接影响后续赛程。"
            return "比赛结果清晰，适合围绕关键团战和失误点切入。"
        if topic_type == "esports_business":
            return "商业和联赛动作更重，适合观察战队经营和生态变化。"
        if topic_type == "esports_controversy":
            return "争议正在放大，重点看选手、俱乐部和官方回应。"
        if topic_type == "esports_star":
            return "明星选手热度明显，适合从个人状态和转会传闻切入。"
        return "电竞信息偏快讯流，先看热度和赛区属性。"
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
    if topic == "platform" and topic_type.startswith("x_"):
        if topic_type == "x_official":
            return "官方账号动作明确，适合继续跟进回应和二次传播。"
        if topic_type == "x_thread":
            return "长帖信息密度更高，适合拆观点、金句和核心判断。"
        if topic_type == "x_reaction":
            return "观点碰撞明显，适合抓争议点和情绪差。"
        return "X 平台传播快，适合看扩散速度和评论区走向。"
    if topic == "platform" and topic_type.startswith("youtube_"):
        if topic_type == "youtube_live":
            return "直播和回放更吃时效，适合提炼片段和关键金句。"
        if topic_type == "youtube_short":
            return "短视频起量更快，适合看强画面和强情绪钩子。"
        if topic_type == "youtube_interview":
            return "访谈和解读更适合拆观点、金句和立场变化。"
        if topic_type == "youtube_trailer":
            return "预告类视频更适合观察期待值和评论反馈。"
        return "视频表达更直观，适合做二创和观点延展。"
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


def full_text(item):
    return " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
            str(item.get("source") or ""),
            str(item.get("repo") or ""),
            " ".join(str(x) for x in item.get("keywords", []) or []),
        ]
    ).strip()


def merge_source_rows(existing_rows, current_rows):
    merged = []
    seen = set()
    for raw in list(existing_rows or []) + list(current_rows or []):
        if not isinstance(raw, dict):
            continue
        source_name = str(raw.get("source") or raw.get("name") or "").strip()
        source_url = str(raw.get("url") or "").strip()
        source_title = clean_title_text(raw.get("title") or "")
        key = (
            normalize_source_name(source_name),
            source_url,
            normalize_title(source_title or source_name),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "source": source_name,
                "title": source_title,
                "url": source_url,
                "domain": domain(source_url),
            }
        )
    return merged


def merge_normalized_item(existing, current):
    existing["sources"] = merge_source_rows(existing.get("sources"), current.get("sources"))
    existing["raw_items"] = list(existing.get("raw_items", [])) + list(current.get("raw_items", []))
    if not existing.get("summary") and current.get("summary"):
        existing["summary"] = current.get("summary")
    existing_keywords = list(existing.get("keywords", []) or [])
    for keyword in current.get("keywords", []) or []:
        if keyword not in existing_keywords:
            existing_keywords.append(keyword)
    existing["keywords"] = existing_keywords

    existing_latest = existing.get("latest_published_at") or existing.get("published_at")
    current_latest = current.get("latest_published_at") or current.get("published_at")
    if isinstance(current_latest, str) and (not existing_latest or current_latest > existing_latest):
        existing["latest_published_at"] = current_latest
        existing["published_at"] = current_latest
        existing["source"] = current.get("source") or existing.get("source")
        existing["url"] = current.get("url") or existing.get("url")
    return existing


def storyline_tags(topic, topic_type, item):
    text = full_text(item)
    tags = []
    for tag, patterns in STORYLINE_PATTERNS.items():
        if any(contains_pattern(text, pattern) for pattern in patterns):
            tags.append(tag)

    forced = {
        "sports_preview": "lineup",
        "sports_result": "result",
        "sports_injury": "injury",
        "sports_transfer": "transfer",
        "sports_controversy": "controversy",
        "sports_star": "star",
        "esports_preview": "lineup",
        "esports_result": "result",
        "esports_business": "business",
        "esports_controversy": "controversy",
        "esports_star": "star",
        "ai_controversy": "controversy",
        "entertainment_controversy": "controversy",
        "x_official": "official",
        "x_thread": "thread",
        "x_reaction": "reaction",
        "youtube_video": "video",
        "youtube_short": "video",
        "youtube_live": "live",
        "youtube_interview": "thread",
        "youtube_trailer": "video",
        "github_automation": "business",
    }.get(topic_type)
    if forced and forced not in tags:
        tags.append(forced)

    if topic == "sports" and re.search(r"\d+\s*[-:比]\s*\d+", item.get("title", "")) and "result" not in tags:
        tags.append("result")
    if topic in {"sports", "esports"} and contains_any(item.get("title", ""), ["vs", "VS", "对阵"]) and "lineup" not in tags:
        tags.append("lineup")
    return [STORYLINE_LABELS[tag] for tag in tags if tag in STORYLINE_LABELS]


def match_keyword_hits(item):
    text = full_text(item).lower()
    hits = []
    for rule in KEYWORD_RULES:
        if any(pattern.lower() in text for pattern in rule["patterns"]):
            hits.append(rule["label"])
    hits.sort(key=lambda label: (-KEYWORD_WEIGHTS.get(label, 0), label))
    return hits


def detect_tags(text, mapping):
    lowered = text.lower()
    matches = []
    for label, patterns in mapping.items():
        if any(pattern.lower() in lowered for pattern in patterns):
            matches.append(label)
    return matches


def detect_league_tags(topic, item):
    if topic not in {"sports", "esports"}:
        return []
    tags = detect_tags(full_text(item), LEAGUE_KEYWORDS)
    explicit = item.get("raw", {}).get("league")
    if isinstance(explicit, str) and explicit and explicit not in tags:
        tags.append(explicit)
    elif isinstance(explicit, list):
        for value in explicit:
            if value and value not in tags:
                tags.append(str(value))
    return tags


def detect_entity_tags(topic, item):
    text = full_text(item)
    tags = detect_tags(text, ENTITY_PATTERNS)
    if topic == "ai":
        subject = extract_ai_subject(item.get("title", ""))
        if subject and subject not in tags:
            tags.append(subject)
    if topic == "entertainment":
        subject = extract_entertainment_subject(item.get("title", ""))
        if subject and subject not in tags:
            tags.append(subject)
    if topic == "github":
        repo = item.get("repo") or ""
        if repo:
            tags.append(repo)
    if topic == "platform":
        platform_label = platform_source_label(item.get("source_topic"))
        if platform_label and platform_label not in tags:
            tags.append(platform_label)
        source = item.get("source") or ""
        if source and source not in tags:
            tags.append(source)
    return tags


def source_count(item):
    sources = item.get("sources")
    if isinstance(sources, list) and sources:
        return len(merge_source_rows(sources, []))
    if item.get("source"):
        return 1
    return 0


def source_quality_text(item) -> str:
    parts = [
        normalize_source_name(item.get("source")),
        str(item.get("source_domain") or ""),
        domain(item.get("url") or ""),
        domain(item.get("source_url") or ""),
    ]
    sources = item.get("sources")
    if isinstance(sources, list):
        for row in sources:
            if not isinstance(row, dict):
                continue
            parts.extend(
                [
                    normalize_source_name(row.get("source") or row.get("name")),
                    str(row.get("domain") or ""),
                    domain(row.get("url") or ""),
                ]
            )
    return " ".join(part for part in parts if part).lower()


def source_quality_tier(item) -> str:
    text = source_quality_text(item)
    if not text:
        return "unknown"
    if any(pattern.lower() in text for pattern in LOW_TRUST_SOURCE_PATTERNS) or is_blocked_source(text):
        return "low"
    if any(pattern.lower() in text for pattern in HIGH_TRUST_SOURCE_PATTERNS):
        return "high"
    if any(pattern.lower() in text for pattern in MEDIUM_TRUST_SOURCE_PATTERNS):
        return "medium"
    if any(pattern.lower() in text for pattern in COMMUNITY_SOURCE_PATTERNS):
        return "community"
    return "normal"


def source_quality_adjustment(item) -> float:
    tier = source_quality_tier(item)
    return {
        "high": 0.8,
        "medium": 0.35,
        "community": -0.2,
        "low": -1.2,
        "unknown": -0.2,
    }.get(tier, 0.0)


def domestic_priority_bonus(topic, item, league_tags, entity_tags):
    if topic not in {"sports", "esports"}:
        return 0.0
    text = full_text(item)
    score = 0.0
    if contains_any(text, DOMESTIC_PRIORITY_PATTERNS):
        score += 0.5
    if any(tag in DOMESTIC_PRIORITY_LEAGUES for tag in league_tags):
        score += 0.35
    if any(tag in DOMESTIC_PRIORITY_ENTITIES for tag in entity_tags):
        score += 0.25
    return round(min(score, 0.9), 2)


def source_score(item):
    topic = str(item.get("topic") or "")
    source_topic = str(item.get("source_topic") or "")
    source = normalize_source_name(item.get("source"))
    count = source_count(item)
    score = 4.0
    for key, weight in SOURCE_SCORE_WEIGHTS.items():
        if key.lower() in source:
            score = 4.5 + weight * 2.0
            break
    if is_blocked_source(source):
        score -= 3.5
    elif any(pattern.lower() in source for pattern in COMMUNITY_SOURCE_PATTERNS):
        score -= 0.8
    if topic == "platform" and source_topic == "x":
        score = max(score, 5.8)
    elif topic == "platform" and source_topic == "youtube":
        score = max(score, 6.2)
    score += source_quality_adjustment(item)
    if count > 1:
        score += min(1.8, (count - 1) * 0.6)
    return round(max(0.0, min(score, 10.0)), 2)


def keyword_score(keyword_hits, entity_tags, domestic_bonus):
    score = 3.5 + sum(KEYWORD_WEIGHTS.get(label, 0) for label in keyword_hits[:5]) * 0.8
    score += min(1.0, len(entity_tags) * 0.25)
    score += domestic_bonus
    return round(max(0.0, min(score, 10.0)), 2)


def topic_fit_score(topic_type, storyline_labels):
    base = {
        "sports_result": 9.0,
        "sports_preview": 8.3,
        "sports_injury": 8.4,
        "sports_transfer": 8.1,
        "sports_controversy": 8.6,
        "sports_star": 7.8,
        "sports_low_value": 2.0,
        "esports_result": 8.7,
        "esports_preview": 8.0,
        "esports_business": 7.2,
        "esports_controversy": 8.1,
        "esports_star": 7.6,
        "esports_hotsearch": 6.5,
        "esports_low_value": 2.0,
        "ai_product": 8.7,
        "ai_model": 8.0,
        "ai_company": 6.8,
        "ai_controversy": 8.1,
        "ai_low_value": 2.0,
        "entertainment_controversy": 8.8,
        "entertainment_movie": 8.0,
        "entertainment_tv": 7.7,
        "entertainment_star": 7.5,
        "entertainment_hotsearch": 6.7,
        "entertainment_low_value": 2.0,
        "x_official": 8.1,
        "x_thread": 7.9,
        "x_reaction": 7.6,
        "x_post": 7.2,
        "x_low_value": 2.0,
        "youtube_live": 8.2,
        "youtube_short": 7.5,
        "youtube_interview": 8.0,
        "youtube_trailer": 7.7,
        "youtube_video": 7.4,
        "youtube_low_value": 2.0,
        "github_ai": 8.6,
        "github_devtool": 8.1,
        "github_automation": 8.4,
        "github_app": 7.4,
        "github_other": 6.4,
    }.get(topic_type, 6.0)
    if storyline_labels:
        base += min(0.6, len(storyline_labels) * 0.15)
    return round(max(0.0, min(base, 10.0)), 2)


def age_hours(parsed_time, reference_time):
    if parsed_time is None:
        return None
    ref = reference_time or datetime.now().astimezone()
    if parsed_time.tzinfo and ref.tzinfo is None:
        ref = ref.astimezone(parsed_time.tzinfo)
    if parsed_time.tzinfo is None and ref.tzinfo is not None:
        parsed_time = parsed_time.replace(tzinfo=ref.tzinfo)
    return (ref - parsed_time).total_seconds() / 3600


def freshness_score(topic, item, reference_time):
    source_topic = str(item.get("source_topic") or "")
    latest = parse_iso_datetime(item.get("latest_published_at") or item.get("published_at"))
    hours = age_hours(latest, reference_time)
    if hours is None:
        return 5.0
    if topic == "platform" and source_topic == "x":
        if hours <= 6:
            return 9.9
        if hours <= 12:
            return 9.4
        if hours <= 24:
            return 8.8
        if hours <= 48:
            return 7.3
        if hours <= 72:
            return 6.1
        return 4.9
    if topic == "platform" and source_topic == "youtube":
        if hours <= 12:
            return 9.5
        if hours <= 24:
            return 8.9
        if hours <= 48:
            return 7.8
        if hours <= 72:
            return 6.8
        if hours <= 24 * 7:
            return 5.8
        return 4.8
    if topic == "github":
        if hours <= 24:
            return 9.7
        if hours <= 72:
            return 8.9
        if hours <= 24 * 7:
            return 7.8
        if hours <= 24 * 14:
            return 6.8
        return 5.6
    if hours <= 6:
        return 9.8
    if hours <= 12:
        return 9.2
    if hours <= 24:
        return 8.5
    if hours <= 48:
        return 7.3
    if hours <= 72:
        return 6.2
    return 4.8


def hotness_score(topic, item, keyword_hits, entity_tags, storyline_labels, domestic_bonus, reference_time):
    score = freshness_score(topic, item, reference_time)
    score += min(1.2, len(keyword_hits) * 0.22)
    score += min(1.0, len(entity_tags) * 0.18)
    score += min(0.8, max(0, source_count(item) - 1) * 0.3)
    score += min(0.8, len(storyline_labels) * 0.12)
    score += domestic_bonus
    return round(max(0.0, min(score, 10.0)), 2)


def build_why_hot(topic, topic_type, item, keyword_hits, entity_tags, storyline_labels, domestic_bonus, reference_time):
    reasons = []
    hours = age_hours(parse_iso_datetime(item.get("latest_published_at") or item.get("published_at")), reference_time)
    if hours is not None:
        if hours <= 12:
            reasons.append("12小时内有更新")
        elif hours <= 24:
            reasons.append("24小时内仍在发酵")
        elif hours <= 72:
            reasons.append("近3天仍有热度")
    if source_count(item) > 1:
        reasons.append(f"{source_count(item)}个来源交叉出现")
    if domestic_bonus >= 0.5:
        reasons.append("国内相关度高")
    type_reason = {
        "sports_result": "赛果驱动强",
        "sports_preview": "赛前关注度高",
        "sports_injury": "伤病变量明显",
        "sports_transfer": "转会推进中",
        "sports_controversy": "争议在扩散",
        "sports_star": "人物热度突出",
        "esports_result": "电竞赛果带动讨论",
        "ai_product": "产品动作明确",
        "ai_controversy": "争议会影响信任",
        "entertainment_controversy": "娱乐争议易出圈",
        "x_official": "平台官方动态清晰",
        "x_thread": "长帖拆解更适合延展",
        "x_reaction": "平台讨论情绪强",
        "youtube_live": "直播内容时效性高",
        "youtube_interview": "访谈信息密度高",
        "youtube_trailer": "预告片更容易带评论区热度",
        "github_automation": "自动化链路清晰",
        "github_ai": "AI 项目关注度高",
    }.get(topic_type)
    if type_reason:
        reasons.append(type_reason)
    if keyword_hits:
        reasons.append("关键词：" + "、".join(keyword_hits[:3]))
    if entity_tags:
        reasons.append("主体：" + "、".join(entity_tags[:3]))
    if item.get("source"):
        reasons.append("来源：" + str(item.get("source")))
    return reasons[:6]


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
    if is_spam_title(title):
        score -= 4.0
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
    if topic == "esports" and contains_any(title, ESPORTS_LOW_VALUE_PATTERNS):
        score -= 1.0
    if topic == "ai" and contains_any(title, ["跑分", "提示词", "曝光"]):
        score -= 0.8
    if topic == "entertainment" and contains_any(title, ENT_LOW_VALUE_PATTERNS):
        score -= 1.5
    if topic == "platform" and contains_any(title, SELF_PROMO_PATTERNS + PLATFORM_LOW_VALUE_PATTERNS):
        score -= 2.0
    if topic == "platform" and platform_video_noise_title(title):
        score -= 2.5
    if topic == "platform" and len(compact) > 84:
        score -= 2.0
    if topic == "platform" and title.count("！") + title.count("!") >= 2:
        score -= 1.2
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
    elif topic == "esports":
        boost = {
            "esports_result": 3.0,
            "esports_preview": 2.4,
            "esports_business": 2.1,
            "esports_controversy": 2.5,
            "esports_star": 2.0,
            "esports_hotsearch": 1.8,
            "esports_low_value": 0.3,
        }
    elif topic == "ai":
        boost = {"ai_product": 3.3, "ai_model": 2.6, "ai_company": 1.6, "ai_controversy": 2.5, "ai_low_value": 0.2}
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
    elif topic == "esports":
        if contains_any(source, ESPORTS_HIGH_VALUE_SOURCES):
            score += 0.8
        if contains_any(title, ESPORTS_LOW_VALUE_PATTERNS):
            score -= 1.0
        if contains_any(title, ["前瞻", "赛前", "vs", "VS", "对阵", "首发", "名单", "预测", "看点"]):
            score += 0.7
        if contains_any(title, ["夺冠", "晋级", "横扫", "翻盘", "卫冕", "击败", "让二追三"]):
            score += 0.9
        if contains_any(title, ["LPL", "KPL", "MSI", "S赛", "世界赛", "英雄联盟", "王者荣耀", "DOTA2", "CS2", "无畏契约"]):
            score += 0.8
        if contains_any(title, ["转会", "续约", "签约", "席位", "版权", "赞助", "联赛"]):
            score += 0.6
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


def build_editor_note(topic, topic_type, title, item):
    if topic == "sports":
        t = title
        if topic_type == "sports_preview":
            if contains_any(t, ["切尔西", "曼联", "平局"]):
                return "英超老对手偏谨慎，平局味道真的很重。"
            if contains_any(t, ["大连英博", "河南"]):
                return "大连英博主场有热度，河南客场不太好打。"
            if contains_any(t, ["选秀", "新秀"]):
                return "新秀题材偏长线，短期不宜当主热点。"
            if contains_any(t, ["杜兰特", "出战成疑"]):
                return "杜兰特状态好坏，直接改这场比赛上限。"
            if contains_any(t, ["vs", "VS", "对阵"]):
                return "对阵有看点，但也要防标题党和噱头。"
            return "赛前类内容先挑强对阵，别被标题带偏。"
        if topic_type == "sports_result":
            if contains_any(t, ["世界波", "破门", "进球"]):
                player = extract_player_from_sports(title)
                if player:
                    return f"{player}这一脚够亮，能单独成一题。"
                return "个人表现够亮，完全能单独写成一条内容。"
            if contains_any(t, ["晋级", "四强", "淘汰"]):
                return "晋级线清楚，下一轮话题还能再拉开。"
            if contains_any(t, ["大胜", "轻取"]):
                return "强弱差距明显，复盘角度也很直接了。"
            if contains_any(t, ["绝平", "救主", "逆转"]):
                return "转折点够强，标题可以写得更狠一点。"
            return "普通赛果价值一般，除非带强队或爆点。"
        if topic_type == "sports_injury":
            return "伤情牵动判断，阵容一变就变盘。"
        if topic_type == "sports_transfer":
            return "转会消息落地慢，热度却能先起。"
        if topic_type == "sports_controversy":
            return "争议一出，后续声音会更乱。"
        if topic_type == "sports_star":
            return "球星个人发挥，往往比赛果更好写。"
        return "普通赛果价值一般，除非带强队或爆点。"

    if topic == "esports":
        t = title
        if topic_type == "esports_preview":
            if contains_any(t, ["LPL", "KPL", "MSI", "S赛", "世界赛"]):
                return "版本和阵容会先影响赛前判断。"
            return "赛前类内容先看阵容和对位，不要只看噱头。"
        if topic_type == "esports_result":
            if contains_any(t, ["夺冠", "卫冕", "晋级", "翻盘", "横扫"]):
                return "赛果已经定调，后续会直接影响赛程和舆论。"
            return "比赛复盘点通常落在团战、运营和关键失误。"
        if topic_type == "esports_business":
            return "商业和联赛动作一出，战队生态会跟着变。"
        if topic_type == "esports_controversy":
            return "争议一旦发酵，俱乐部和选手都会被推上台面。"
        if topic_type == "esports_star":
            return "明星选手是流量入口，个人状态最能带题。"
        if topic_type == "esports_low_value":
            return "信息偏边角，优先级不如赛果和转会。"
        return "电竞信息密度高，先看赛区、战队和版本关键词。"

    if topic == "ai":
        t = title
        low = t.lower()
        if topic_type == "ai_product":
            if contains_any(t, ["OpenAI", "ChatGPT"]):
                return "OpenAI在把 Agent 推向真实电脑操作场景。"
            if contains_any(t, ["Claude", "涨价", "降智"]):
                return "Claude这波争议，伤到的是付费信任。"
            if contains_any(t, ["地平线", "舱驾", "座舱", "腾讯", "出行"]):
                return "智能体开始进入汽车和出行场景，落地信号更明确。"
            if contains_any(t, ["Copilot", "GitHub"]):
                return "Copilot正在变成多模型开发入口。"
            if contains_any(t, ["英伟达"]):
                return "英伟达继续把 AI 塞进行业基础设施层。"
            if contains_any(t, ["阿里", "Meoo", "零代码"]):
                return "阿里这条更像低门槛建站和开发工具。"
            if contains_any(t, ["智能体"]):
                return "智能体开始进入企业流程控制层。"
            if contains_any(t, ["XR", "Meta", "谷歌"]):
                return "XR开发正在成为 AI 工具新落点。"
            if contains_any(t, ["工具", "插件", "代码"]):
                return "工具属性很强，上手和接入速度最关键。"
            return "行业稿偏多，先留产品更新和落地信号。"
        if topic_type == "ai_model":
            return "模型变化是核心，效果提升最重要。"
        if topic_type == "ai_controversy":
            if contains_any(t, ["安全", "治理", "大会", "发展"]) and not contains_any(t, ["泄露", "诉讼", "崩", "翻车", "降智"]):
                return "AI安全和治理议题升温，行业讨论会继续增加。"
            return "争议会冲击信任，付费逻辑也会受压。"
        return "行业稿偏多，先留产品更新和落地信号。"

    if topic == "entertainment":
        t = title
        if contains_any(t, ["白玉兰", "金鸡", "金像", "提名", "获奖"]):
            return "奖项和提名带动人物讨论，后续关注获奖名单和口碑。"
        if contains_any(t, ["品牌翻车", "终止合作", "致歉"]):
            return "品牌翻车牵出艺人切割，舆论还会继续烧。"
        if contains_any(t, ["微电影", "影片", "电影", "五一", "定档", "上映"]):
            return "影视档期和片单已经明确，后续看票房和观众反馈。"
        if contains_any(t, ["陈思诚", "10间敢死队"]):
            return "陈思诚新片看点在新人阵容和口碑反应。"
        if contains_any(t, ["乘风", "李小冉"]):
            return "李小冉反差感，成了这波综艺入口之一。"
        if contains_any(t, ["定档"]) and contains_any(t, ["《", "》"]):
            return "新片进入宣发，演员组合决定最终声量。"
        if contains_any(t, ["电影节", "北影节"]):
            return "电影节内容偏行业，先挑明星和作品亮点。"
        if contains_any(t, ["营收", "净利", "票房"]):
            return "影视行业热闹背后，利润压力更刺眼。"
        return "娱乐资讯太散，先挑冲突和人物线。"

    if topic == "platform" and topic_type.startswith("x_"):
        if topic_type == "x_official":
            return "官方账号一发声，后续转述会迅速跟上。"
        if topic_type == "x_thread":
            return "长帖别只摘一句，核心论点更值钱。"
        if topic_type == "x_reaction":
            return "情绪值高，但要筛掉纯吵架内容。"
        return "X 传播极快，评论区和二次扩散都要盯。"

    if topic == "platform" and topic_type.startswith("youtube_"):
        if topic_type == "youtube_live":
            return "直播类先截关键段，再补背景和上下文。"
        if topic_type == "youtube_short":
            return "短视频重点看第一眼钩子够不够强。"
        if topic_type == "youtube_interview":
            return "访谈类内容，金句和立场变化最重要。"
        if topic_type == "youtube_trailer":
            return "预告片要先看评论区和期待值变化。"
        return "视频选题先抓核心段落，再决定怎么拆。"

    if topic == "github":
        if any(k in title.lower() for k in ["career-ops"]):
            return "求职流程自动化，适合拆效率工具案例。"
        if any(k in title.lower() for k in ["everything-claude-code"]):
            return "Claude Code工具集合，开发者会感兴趣。"
        if any(k in title.lower() for k in ["hermes-agent"]):
            return "长期记忆 Agent，个人助手方向更明确。"
        if any(k in title.lower() for k in ["openhands"]):
            return "自动编程代表项目，边界感和风险都清楚。"
        if any(k in title.lower() for k in ["chattts"]):
            return "语音生成场景清晰，内容生产能直接上。"
        if any(k in title.lower() for k in ["ragflow"]):
            return "RAG知识库方向明确，企业场景会更强。"
        if any(k in title.lower() for k in ["llamafactory"]):
            return "微调门槛降低，开源模型训练更顺手。"
        if any(k in title.lower() for k in ["huginn", "browser-use", "airflow", "n8n"]):
            return "自动化属性强，能接采集和发布链路。"
        if topic_type == "github_ai":
            return "AI项目不少，关键看能不能真实落地。"
        if topic_type == "github_devtool":
            return "开发工具类先看上手成本和接入难度。"
        if topic_type == "github_automation":
            return "自动化项目看能不能替代重复流程操作。"
        if topic_type == "github_app":
            return "应用型项目更直观，产品形态一看就懂。"
        return "开源项目热度在起，维护节奏和社区反馈要盯住。"

    return "先看标题爆点，再决定值不值得跟进。"


def editor_note(topic, topic_type, title, item):
    note = build_editor_note(topic, topic_type, title, item)
    for bad in EDITOR_NOTE_BANNED:
        note = note.replace(bad, "")
    note = re.sub(r"[，,。]{2,}", "。", note).strip("。 ，,")
    if len(note) > 42:
        note = note[:42]
        note = note.rstrip("，。 ，,")
    if len(note) < 16:
        fallback = {
            "sports": "先看标题爆点，再决定值不值得跟。",
            "esports": "先看版本强弱，再判断值不值得跟。",
            "ai": "先看产品落地，再判断题材热不热。",
            "entertainment": "先看人物冲突，再判断能不能写。",
            "platform": "先看扩散和评论，再判断值不值得拆。",
            "github": "先看项目用途，再判断能不能追。",
        }.get(topic, "先看标题爆点，再决定值不值得跟。")
        note = fallback
    return note


def _text_contains_all(text, needles):
    lowered = str(text or "").lower()
    return all(str(needle).lower() in lowered for needle in needles)


def _text_contains_any(text, needles):
    lowered = str(text or "").lower()
    return any(str(needle).lower() in lowered for needle in needles)


def editorial_rule_matches(rule, item):
    if not isinstance(rule, dict):
        return False
    match = rule.get("match") or {}
    if not isinstance(match, dict):
        return False
    for field in ("topic", "source_topic", "topic_type", "source"):
        expected = match.get(field)
        if expected and str(item.get(field) or "") != str(expected):
            return False
    if match.get("title_contains") and not _text_contains_all(item.get("title"), [match["title_contains"]]):
        return False
    if match.get("title_contains_any") and not _text_contains_any(item.get("title"), match.get("title_contains_any") or []):
        return False
    if match.get("source_contains") and not _text_contains_all(item.get("source"), [match["source_contains"]]):
        return False
    if match.get("source_contains_any") and not _text_contains_any(item.get("source"), match.get("source_contains_any") or []):
        return False
    if match.get("repo_contains") and not _text_contains_all(item.get("repo"), [match["repo_contains"]]):
        return False
    if match.get("url_contains") and not _text_contains_all(item.get("url"), [match["url_contains"]]):
        return False
    return True


def apply_editorial_overrides(item):
    payload = load_editorial_overrides()
    rules = payload.get("rules") or []
    score_delta = 0.0
    pin_rank = None
    hidden = False
    for rule in rules:
        if not editorial_rule_matches(rule, item):
            continue
        actions = rule.get("actions") or {}
        if not isinstance(actions, dict):
            continue
        if actions.get("hide"):
            hidden = True
        if "score_delta" in actions:
            try:
                score_delta += float(actions.get("score_delta") or 0)
            except (TypeError, ValueError):
                pass
        if "pin_rank" in actions:
            try:
                current = int(actions.get("pin_rank"))
                pin_rank = current if pin_rank is None else min(pin_rank, current)
            except (TypeError, ValueError):
                pass
        for field, key in (("title", "title"), ("summary_hint", "summary_hint"), ("editor_note", "editor_note"), ("reference_url", "url")):
            if actions.get(key):
                item[field] = str(actions[key]).strip()
        if actions.get("add_storyline_tags") and isinstance(actions.get("add_storyline_tags"), list):
            item["storyline_tags"] = list(dict.fromkeys(list(item.get("storyline_tags") or []) + [str(v) for v in actions["add_storyline_tags"] if v]))
        if actions.get("add_why_hot") and isinstance(actions.get("add_why_hot"), list):
            item["why_hot"] = list(dict.fromkeys(list(item.get("why_hot") or []) + [str(v) for v in actions["add_why_hot"] if v]))[:8]
    item["editorial_hidden"] = hidden
    item["editorial_score_delta"] = round(score_delta, 2)
    if pin_rank is not None:
        item["pin_rank"] = pin_rank
    return item


def dedupe_items(items):
    merged_by_topic = defaultdict(list)
    for raw in [normalize_item(x) for x in items]:
        if not raw["title"]:
            continue
        if is_spam_title(raw["title"]) or is_spam_title(full_text(raw)):
            continue
        source_topic = infer_topic(raw)
        topic = canonical_topic(source_topic)
        raw["source_topic"] = source_topic
        raw["topic"] = topic
        dup_threshold = {"sports": 0.96, "ai": 0.88, "entertainment": 0.90, "github": 0.90, "platform": 0.93}.get(topic, 0.90)
        matched = None
        for prev in merged_by_topic[topic]:
            if normalize_title(prev["title"]) == normalize_title(raw["title"]):
                matched = prev
                break
            if title_similarity(prev["title"], raw["title"]) >= dup_threshold:
                matched = prev
                break
        if matched is not None:
            merge_normalized_item(matched, raw)
        else:
            merged_by_topic[topic].append(raw)

    ordered = []
    for topic in TOPIC_ORDER:
        ordered.extend(merged_by_topic.get(topic, []))
    return ordered


def build_ranked(items, top, reference_time=None):
    normalized = dedupe_items(items)
    ranked = []

    for item in normalized:
        topic = item["topic"]
        source_topic = str(item.get("source_topic") or topic)
        topic_type = infer_topic_type(topic, item)
        storyline_labels = storyline_tags(topic, topic_type, item)
        keyword_hits = match_keyword_hits(item)
        league_tags = detect_league_tags(topic, item)
        entity_tags = detect_entity_tags(topic, item)
        domestic_bonus = domestic_priority_bonus(topic, item, league_tags, entity_tags)
        hotness = hotness_score(topic, item, keyword_hits, entity_tags, storyline_labels, domestic_bonus, reference_time)
        topic_fit = topic_fit_score(topic_type, storyline_labels)
        src_score = source_score(item)
        kw_score = keyword_score(keyword_hits, entity_tags, domestic_bonus)
        title_score = title_quality_score(topic, item["title"])
        total_score = round(
            min(
                10.0,
                hotness * 0.35
                + topic_fit * 0.25
                + src_score * 0.20
                + kw_score * 0.15
                + title_score * 0.05,
            ),
            2,
        )
        output_title = item.get("display_title") or item["title"]
        output_summary = item.get("display_summary") or item.get("summary") or ""
        original_title = item.get("original_title") or item["title"]
        original_summary = item.get("original_summary") or item.get("summary") or ""
        note = editor_note(topic, topic_type, item["title"], item)
        summary_line = summary_hint(topic, topic_type, item["title"])
        sources = merge_source_rows(
            item.get("sources"),
            [
                {
                    "source": item.get("source", ""),
                    "title": item.get("title", ""),
                    "url": item.get("source_url") or item.get("url", ""),
                    "domain": domain(item.get("source_url") or item.get("url", "")),
                }
            ],
        )
        primary_source_domain = ""
        for source_row in sources:
            if source_row.get("domain"):
                primary_source_domain = source_row.get("domain", "")
                break
        out = {
            "title": output_title,
            "summary": output_summary,
            "source": item["source"],
            "url": item["url"],
            "reference_url": item["url"],
            "topic": topic,
            "topic_label": TOPIC_LABELS.get(topic, topic),
            "source_topic": source_topic,
            "topic_type": topic_type,
            "score": total_score,
            "total_score": total_score,
            "summary_hint": summary_line,
            "editor_note": note,
            "sources": sources,
            "source_domain": primary_source_domain,
            "source_count": source_count({"sources": sources, "source": item.get("source")}),
            "source_quality_tier": source_quality_tier({**item, "sources": sources, "source_domain": primary_source_domain}),
            "published_at": item.get("published_at"),
            "latest_published_at": item.get("latest_published_at") or item.get("published_at"),
            "storyline_tags": storyline_labels,
            "keyword_hits": keyword_hits,
            "league_tags": league_tags,
            "entity_tags": entity_tags,
            "score_breakdown": {
                "hotness_score": hotness,
                "topic_fit_score": topic_fit,
                "source_score": src_score,
                "keyword_score": kw_score,
                "title_quality_score": title_score,
            },
            "why_hot": build_why_hot(topic, topic_type, item, keyword_hits, entity_tags, storyline_labels, domestic_bonus, reference_time),
            "raw": item.get("raw") or {},
        }
        if topic == "platform":
            out["platform_source"] = source_topic
            out["platform_label"] = platform_source_label(source_topic)
        if output_title and output_title != original_title:
            out["original_title"] = original_title
        if output_summary and output_summary != original_summary:
            out["original_summary"] = original_summary
        if topic == "github":
            github_raw_title = out.get("title") or ""
            out["repo"] = item.get("repo") or ""
            out["stars"] = int(item.get("stars") or 0)
            out["forks"] = int(item.get("forks") or 0)
            out["language"] = item.get("language")
            out["created_at"] = item.get("created_at") or item.get("published_at")
            out["raw_summary"] = item.get("summary") or item.get("description") or ""
            out["summary"] = build_github_zh_summary(out)
            out["recommend_reason"] = build_github_recommend_reason(out)
            if out["repo"]:
                out["title"] = out["repo"]
                if github_raw_title and github_raw_title != out["repo"]:
                    out["original_title"] = github_raw_title
        if topic == "entertainment" and topic_type == "entertainment_controversy":
            out["event_key"] = ent_event_key(item["title"])
        out = apply_editorial_overrides(out)
        delta = float(out.pop("editorial_score_delta", 0) or 0)
        if delta:
            adjusted = round(max(0.0, min(10.0, float(out["total_score"]) + delta)), 2)
            out["total_score"] = adjusted
            out["score"] = adjusted
        if not out.get("editorial_hidden"):
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

    final_ranked.sort(key=lambda x: (x.get("pin_rank") is None, x.get("pin_rank", 9999), -float(x["score"])), reverse=False)

    grouped = defaultdict(list)
    for item in final_ranked:
        grouped[item["topic"]].append(item)

    final = []
    for topic in TOPIC_ORDER:
        source_counts = Counter()
        selected = []
        for item in grouped[topic]:
            source_name = item.get("source", "") or "未知来源"
            cap = 5 if topic in {"sports", "esports"} else 8
            if topic != "github" and source_counts[source_name] >= cap:
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

    if any(k in repo for k in ["career-ops"]):
        return "把求职流程自动化，适合拆成效率工具案例。"
    if any(k in repo for k in ["everything-claude-code"]):
        return "围绕 Claude Code 堆工具，开发者味道很重。"
    if any(k in repo for k in ["hermes-agent"]):
        return "长期记忆 Agent 方向明确，适合继续跟踪。"
    if any(k in repo for k in ["openhands"]):
        return "AI接管开发任务，属于自动编程代表。"
    if any(k in repo for k in ["chattts"]):
        return "语音生成场景明确，适合内容生产选题。"
    if any(k in repo for k in ["ragflow"]):
        return "RAG和知识库结合紧，适合企业文档问答。"
    if any(k in repo for k in ["llamafactory"]):
        return "微调门槛降低，适合追踪开源模型训练工具。"
    if any(k in repo for k in ["huginn", "browser-use", "airflow", "n8n"]):
        return "自动化流程价值明确，适合接入采集和发布链路。"

    parts = []
    if stars > 100000:
        parts.append("社区规模大")
    if topic_type == "github_automation":
        parts.append("自动化链路清晰")
    elif topic_type == "github_devtool":
        parts.append("开发效率导向明显")
    elif topic_type == "github_ai":
        parts.append("AI/Agent 方向明确")
    elif topic_type == "github_app":
        parts.append("应用落地路径清晰")
    if created_days is not None and created_days <= 30:
        parts.append("近期新项目")
    if pushed_days is not None and pushed_days <= 7:
        parts.append("近期仍活跃")
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
            lines.append(f"- total_score：{item.get('total_score', item.get('score'))}")
            if item.get("storyline_tags"):
                lines.append(f"- storyline_tags：{'、'.join(item['storyline_tags'])}")
            lines.append(f"- 概述：{item['editor_note'] or item['summary_hint']}")
            if item.get("why_hot"):
                lines.append(f"- 上榜原因：{'；'.join(item['why_hot'][:3])}")
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
    reference_time = datetime.fromisoformat(args.reference_time) if args.reference_time else datetime.now().astimezone()
    ranked = build_ranked(raw_items, args.top, reference_time=reference_time)
    counts = Counter(x["topic"] for x in ranked)
    payload = {
        "items": ranked,
        "topic_counts": dict(counts),
        "reference_time": reference_time.isoformat(),
    }

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
    return build_ranked(items, top, reference_time=reference_time)


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
