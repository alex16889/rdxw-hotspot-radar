import json
import os
import tempfile
import unittest
import builtins
from datetime import datetime
from pathlib import Path

import run_daily_hotspots as runner
from run_daily_hotspots import (
    apply_llm_editorial_patch,
    build_item_longtail,
    build_heat_index_payload,
    build_interpretation_candidates_payload,
    build_daily_brief_payload,
    build_seo_cluster_pages,
    build_window_items,
    build_source_quality_payload,
    compact_window_payload,
    decode_google_news_article_url,
    enrich_item_for_publication,
    fetch_overseas_real_sources,
    build_health_payload,
    is_spam_or_ad_title,
    llm_error_is_known_non_core,
    load_source_radar_sources,
    load_cached_source_radar_card,
    low_value_item_title,
    normalize_source_radar_item,
    normalize_hacker_news_item,
    normalize_reddit_post,
    overseas_source_stats_from_items,
    parse_techmeme_feed,
    resolve_reference_url,
    semantic_merge_ranked_items,
    write_cached_source_radar_card,
    source_radar_timestamp,
    write_split_topic_payloads,
    write_static_site_outputs,
)
from transform import hotspot_pipeline
from transform.hotspot_pipeline import build_ranked, source_quality_tier


class HotspotPipelineTests(unittest.TestCase):
    def tearDown(self):
        hotspot_pipeline.load_editorial_overrides.cache_clear()

    def test_html_summary_is_cleaned(self):
        items = [
            {
                "title": "中超-杨希建功克雷桑任意球救主 泰山1-1海港",
                "summary": '<a href="https://example.com/story">中超-杨希建功克雷桑任意球救主 泰山1-1海港</a><font color="#6f6f6f">央视体育</font>',
                "source": "央视体育",
                "url": "https://example.com/story",
                "published_at": "2026-04-24T10:00:00+08:00",
                "topic": "sports",
            }
        ]
        ranked = build_ranked(items, top=10)
        self.assertEqual(len(ranked), 1)
        self.assertNotIn("<a", ranked[0].get("summary", ""))
        self.assertNotIn("<font", ranked[0].get("summary", ""))

    def test_platform_items_are_merged_under_platform_topic(self):
        items = [
            {
                "title": "OpenAI 发布新演示视频",
                "translated_title": "OpenAI 发布新演示视频",
                "summary": "官方视频",
                "source": "YouTube",
                "url": "https://youtube.com/watch?v=abc",
                "published_at": "2026-04-24T10:00:00+08:00",
                "topic": "youtube",
            },
            {
                "title": "OpenAI 发布新帖文",
                "translated_title": "OpenAI 发布新帖文",
                "summary": "官方账号发文",
                "source": "X",
                "url": "https://x.com/openai/status/1",
                "published_at": "2026-04-24T10:30:00+08:00",
                "topic": "x",
            },
        ]
        ranked = build_ranked(items, top=10)
        self.assertTrue(all(item["topic"] == "platform" for item in ranked))
        self.assertEqual({item["platform_source"] for item in ranked}, {"youtube", "x"})

    def test_platform_technical_stream_titles_are_low_value(self):
        self.assertTrue(low_value_item_title("youtube", "直播!｜T4｜Q 第2天｜WTT 支线赛 Senec 2026｜第一节"))
        self.assertFalse(low_value_item_title("sports", "直播!｜T4｜Q 第2天｜WTT 支线赛 Senec 2026｜第一节"))

    def test_platform_generic_youtube_serials_are_low_value(self):
        title = "Maa Inti Devatha Official Promo | 14 May 2026 | Telugu Serial"
        self.assertTrue(low_value_item_title("youtube", title))
        self.assertEqual(
            hotspot_pipeline.infer_youtube_type({"title": title, "summary": "", "url": "https://youtube.com/watch?v=1"}),
            "youtube_low_value",
        )
        self.assertFalse(low_value_item_title("youtube", "OpenAI 发布 GPT 新模型演示视频"))

    def test_platform_spam_result_titles_are_low_value(self):
        title = 'Results for " 搜狐 体育 nba｛官网：701.tw｝.gxz'
        self.assertTrue(low_value_item_title("platform", title))
        self.assertTrue(low_value_item_title("x", title))
        current_spam = '"IM电竞官方 85136.vipKpT" - Results on X｜直播 Posts & Updates'
        self.assertTrue(is_spam_or_ad_title(current_spam))
        self.assertTrue(low_value_item_title("platform", current_spam))
        self.assertEqual(
            build_ranked(
                [
                    {
                        "title": current_spam,
                        "source": "X",
                        "url": "https://x.com/search?q=spam",
                        "published_at": "2026-04-24T10:00:00+08:00",
                        "topic": "x",
                    }
                ],
                top=10,
            ),
            [],
        )
        signature_spam = "😃 🌟 🤗 😁 🎊 🌸 英超 世界杯 女足亚洲杯 爱新体育 英格兰超级联赛 点击签名复制链接@Rk2qTo"
        self.assertTrue(is_spam_or_ad_title(signature_spam))
        self.assertTrue(low_value_item_title("platform", signature_spam))

    def test_hacker_news_item_is_normalized_as_overseas_ai_signal(self):
        item = normalize_hacker_news_item(
            {
                "id": 123,
                "type": "story",
                "title": "OpenAI releases a new agent SDK",
                "url": "https://openai.com/index/agents-sdk",
                "score": 356,
                "descendants": 88,
                "time": 1780000000,
            },
            "top",
        )
        self.assertIsNotNone(item)
        self.assertEqual(item["source"], "Hacker News")
        self.assertEqual(item["topic"], "ai")
        self.assertTrue(item["overseas_signal"])
        self.assertIn("356 分", item["summary"])
        self.assertEqual(item["source_url"], "https://news.ycombinator.com/item?id=123")

    def test_techmeme_feed_is_parsed_as_overseas_ai_signal(self):
        xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Techmeme</title>
<item>
  <title>Anthropic launches Claude for enterprise teams</title>
  <link>https://example.com/anthropic</link>
  <description><![CDATA[Enterprise AI rollout coverage.]]></description>
  <pubDate>Wed, 08 Jul 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""
        items = parse_techmeme_feed(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "Techmeme")
        self.assertEqual(items[0]["topic"], "ai")
        self.assertTrue(items[0]["overseas_signal"])
        self.assertEqual(items[0]["url"], "https://example.com/anthropic")

    def test_reddit_post_is_normalized_as_overseas_signal(self):
        item = normalize_reddit_post(
            {
                "data": {
                    "title": "OpenAI launches a new developer agent",
                    "subreddit": "OpenAI",
                    "permalink": "/r/OpenAI/comments/abc/openai_agent/",
                    "url": "https://openai.com/index/agents/",
                    "score": 1280,
                    "num_comments": 240,
                    "created_utc": 1780000000,
                }
            },
            "OpenAI",
        )
        self.assertIsNotNone(item)
        self.assertEqual(item["source"], "Reddit r/OpenAI")
        self.assertEqual(item["topic"], "ai")
        self.assertEqual(item["source_topic"], "reddit")
        self.assertTrue(item["overseas_signal"])
        self.assertIn("1280 分", item["summary"])
        self.assertEqual(item["source_url"], "https://www.reddit.com/r/OpenAI/comments/abc/openai_agent/")

    def test_reddit_source_is_pending_without_credentials(self):
        old_client_id = os.environ.pop("REDDIT_CLIENT_ID", None)
        old_client_secret = os.environ.pop("REDDIT_CLIENT_SECRET", None)
        try:
            items, stats = runner.fetch_reddit_hot_posts()
        finally:
            if old_client_id is not None:
                os.environ["REDDIT_CLIENT_ID"] = old_client_id
            if old_client_secret is not None:
                os.environ["REDDIT_CLIENT_SECRET"] = old_client_secret
        self.assertEqual(items, [])
        self.assertEqual(stats[0]["name"], "reddit_api")
        self.assertEqual(stats[0]["status"], "pending_credentials")

    def test_overseas_real_sources_collects_stats(self):
        original_hn = runner.fetch_hacker_news_stories
        original_techmeme = runner.fetch_techmeme_rss
        original_reddit = runner.fetch_reddit_hot_posts
        try:
            runner.fetch_hacker_news_stories = lambda kind, limit=24: [
                {
                    "title": f"{kind} story",
                    "source": "Hacker News",
                    "url": "https://news.ycombinator.com/item?id=1",
                    "topic": "ai",
                    "source_topic": "overseas",
                }
            ]
            runner.fetch_techmeme_rss = lambda: [
                {
                    "title": "Techmeme story",
                    "source": "Techmeme",
                    "url": "https://example.com/tech",
                    "topic": "ai",
                    "source_topic": "overseas",
                }
            ]
            runner.fetch_reddit_hot_posts = lambda: (
                [
                    {
                        "title": "Reddit story",
                        "source": "Reddit r/OpenAI",
                        "url": "https://www.reddit.com/r/OpenAI/comments/abc/story/",
                        "topic": "ai",
                        "source_topic": "reddit",
                    }
                ],
                [{"topic": "ai", "name": "reddit_openai", "count": 1}],
            )
            items, stats = fetch_overseas_real_sources()
        finally:
            runner.fetch_hacker_news_stories = original_hn
            runner.fetch_techmeme_rss = original_techmeme
            runner.fetch_reddit_hot_posts = original_reddit
        self.assertEqual(len(items), 4)
        self.assertEqual(
            {row["name"]: row["count"] for row in stats},
            {"hackernews_topstories": 1, "hackernews_beststories": 1, "techmeme_rss": 1, "reddit_openai": 1},
        )

    def test_overseas_source_stats_counts_raw_sources(self):
        stats = overseas_source_stats_from_items(
            [
                {
                    "title": "HN story",
                    "source": "Hacker News",
                    "topic": "ai",
                    "overseas_signal": True,
                    "url": "https://news.ycombinator.com/item?id=1",
                },
                {
                    "title": "Techmeme story",
                    "source": "Techmeme",
                    "topic": "ai",
                    "overseas_signal": True,
                    "url": "https://www.techmeme.com/250708/p1#a250708p1",
                },
                {
                    "title": "GitHub repo",
                    "topic": "github",
                    "source": "GitHub",
                    "url": "https://github.com/example/repo",
                },
                {
                    "title": "Reddit story",
                    "topic": "ai",
                    "source": "Reddit r/OpenAI",
                    "source_topic": "reddit",
                    "url": "https://www.reddit.com/r/OpenAI/comments/abc/story/",
                },
            ]
        )
        self.assertEqual(stats["Hacker News"], 1)
        self.assertEqual(stats["Techmeme"], 1)
        self.assertEqual(stats["GitHub"], 1)
        self.assertEqual(stats["Reddit"], 1)

    def test_signature_spam_is_excluded_from_public_outputs(self):
        signature_spam = "😃 🌟 🤗 😁 🎊 🌸 英超 世界杯 女足亚洲杯 爱新体育 英格兰超级联赛 点击签名复制链接@Rk2qTo"
        ranked_payload = {
            "run_date": "2026-06-12",
            "reference_time": "2026-06-12T09:00:00+08:00",
            "items": [
                {
                    "topic": "platform",
                    "topic_label": "平台热议",
                    "hotspot_id": "spam",
                    "detail_path": "hot/platform/spam.html",
                    "title": signature_spam,
                    "summary": "签名引流噪声。",
                    "source": "X",
                    "url": "https://x.com/search?q=spam",
                    "published_at": "2026-06-12T08:30:00+08:00",
                    "total_score": 9.8,
                },
                {
                    "topic": "sports",
                    "topic_label": "体育热点",
                    "hotspot_id": "mexico-win",
                    "detail_path": "hot/sports/mexico-win.html",
                    "title": "墨西哥2-0南非取得世界杯揭幕战开门红",
                    "summary": "墨西哥赢下揭幕战。",
                    "source": "新华社",
                    "url": "https://example.com/mexico",
                    "published_at": "2026-06-12T08:40:00+08:00",
                    "total_score": 9.4,
                    "editorial_value_score": 9.4,
                    "editorial_value_level": "强选题",
                    "sources": [
                        {"source": "新华社", "domain": "news.cn", "url": "https://example.com/1"},
                        {"source": "FIFA", "domain": "fifa.com", "url": "https://example.com/2"},
                        {"source": "AP", "domain": "apnews.com", "url": "https://example.com/3"},
                    ],
                },
            ],
        }
        windows_payload = {"windows": {"7d": {"items": ranked_payload["items"]}}}
        self.assertNotIn(signature_spam, [row["title"] for row in runner.collect_daily_longtail_items(ranked_payload, 10)])
        self.assertNotIn(signature_spam, [row["title"] for row in build_heat_index_payload(ranked_payload, windows_payload)["items"]])
        self.assertNotIn(signature_spam, [row["title"] for row in runner.collect_detail_items(ranked_payload, windows_payload)])

    def test_low_value_ai_policy_is_classified(self):
        ranked = build_ranked(
            [
                {
                    "title": "国家档案局发布人工智能司法应用指南",
                    "summary": "行业政策动态",
                    "source": "人民网",
                    "url": "https://example.com/ai-policy",
                    "published_at": "2026-04-24T10:00:00+08:00",
                    "topic": "ai",
                }
            ],
            top=10,
        )
        self.assertEqual(ranked[0]["topic_type"], "ai_low_value")

    def test_entertainment_pr_event_is_classified_low_value(self):
        ranked = build_ranked(
            [
                {
                    "title": "北影节论坛在中国电影博物馆启动",
                    "summary": "活动现场发布多项计划",
                    "source": "人民网",
                    "url": "https://example.com/ent-pr",
                    "published_at": "2026-04-24T10:00:00+08:00",
                    "topic": "entertainment",
                }
            ],
            top=10,
        )
        self.assertEqual(ranked[0]["topic_type"], "entertainment_low_value")

    def test_window_items_clean_esports_source_suffix(self):
        reference_time = datetime.fromisoformat("2026-04-24T12:00:00+07:00")
        dirty_title = "LPL 4月24日首发：Photic作为OMG首发AD上场，Renard对位HongQ - 遥远的布莱梅 - Score-电竞玩家赛事社区"
        window_items = build_window_items(
            [
                (
                    reference_time,
                    {
                        "items": [
                            {
                                "title": dirty_title,
                                "summary": "LPL首发名单",
                                "source": "Score-电竞玩家赛事社区",
                                "url": "https://example.com/esports",
                                "published_at": "2026-04-24T10:00:00+08:00",
                                "latest_published_at": "2026-04-24T10:00:00+08:00",
                                "topic": "esports",
                                "topic_type": "esports_preview",
                                "total_score": 8.0,
                                "sources": [
                                    {
                                        "source": "scoregg.com",
                                        "title": dirty_title,
                                        "url": "https://example.com/esports",
                                    }
                                ],
                            }
                        ]
                    },
                )
            ],
            window_days=7,
            top=10,
            reference_time=reference_time,
        )
        self.assertEqual(len(window_items), 1)
        self.assertNotIn("Score-电竞玩家赛事社区", window_items[0]["title"])
        self.assertNotIn("遥远的布莱梅", window_items[0]["title"])
        self.assertNotIn("Score-电竞玩家赛事社区", window_items[0]["sources"][0]["title"])
        self.assertNotIn("遥远的布莱梅", window_items[0]["sources"][0]["title"])

    def test_editorial_override_can_hide_and_pin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            override_path = Path(tmpdir) / "editorial.json"
            override_path.write_text(
                json.dumps(
                    {
                        "rules": [
                            {
                                "match": {"topic": "sports", "title_contains": "隐藏"},
                                "actions": {"hide": True},
                            },
                            {
                                "match": {"topic": "sports", "title_contains": "置顶"},
                                "actions": {"pin_rank": 1, "score_delta": 0.5},
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.environ["HOTSPOT_EDITORIAL_PATH"] = str(override_path)
            hotspot_pipeline.load_editorial_overrides.cache_clear()
            items = [
                {
                    "title": "普通体育新闻",
                    "summary": "普通内容",
                    "source": "央视体育",
                    "url": "https://example.com/1",
                    "published_at": "2026-04-24T10:00:00+08:00",
                    "topic": "sports",
                },
                {
                    "title": "置顶体育新闻",
                    "summary": "重点内容",
                    "source": "央视体育",
                    "url": "https://example.com/2",
                    "published_at": "2026-04-24T10:00:00+08:00",
                    "topic": "sports",
                },
                {
                    "title": "隐藏体育新闻",
                    "summary": "不应展示",
                    "source": "央视体育",
                    "url": "https://example.com/3",
                    "published_at": "2026-04-24T10:00:00+08:00",
                    "topic": "sports",
                },
            ]
            ranked = build_ranked(items, top=10)
            self.assertEqual(ranked[0]["title"], "置顶体育新闻")
            self.assertFalse(any(item["title"] == "隐藏体育新闻" for item in ranked))
        os.environ.pop("HOTSPOT_EDITORIAL_PATH", None)

    def test_split_manifest_writes_topic_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            ranked_payload = {
                "run_date": "2026-04-24",
                "reference_time": "2026-04-24T12:00:00+07:00",
                "topic_labels": {
                    "sports": "体育热点",
                    "esports": "电竞热点",
                    "ai": "AI科技热点",
                    "entertainment": "泛娱乐热点",
                    "platform": "平台热议",
                    "github": "GitHub热点项目",
                },
            }
            windows_payload = {
                "generated_at": "2026-04-24T12:00:00+07:00",
                "available_windows": [
                    {"key": "1d", "label": "24小时", "days": 1},
                    {"key": "3d", "label": "3天", "days": 3},
                    {"key": "7d", "label": "7天", "days": 7},
                ],
                "windows": {
                    "1d": {
                        "topic_counts": {"sports": 1},
                        "items": [{"topic": "sports", "title": "体育新闻"}],
                    },
                    "3d": {"topic_counts": {}, "items": []},
                    "7d": {"topic_counts": {}, "items": []},
                },
            }
            manifest_path = write_split_topic_payloads(output_dir, ranked_payload, windows_payload)
            self.assertTrue(manifest_path.exists())
            sports_payload = json.loads((output_dir / "topics" / "1d_sports.json").read_text(encoding="utf-8"))
            self.assertEqual(sports_payload["topic"], "sports")
            self.assertEqual(sports_payload["item_count"], 1)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_radar"], "source_radar.json")
            self.assertEqual(manifest["source_quality"], "source_quality.json")
            self.assertIn("detail_url", sports_payload["items"][0])

            compact = compact_window_payload(windows_payload)
            self.assertEqual(compact["windows"]["1d"]["item_count"], 1)
            self.assertNotIn("items", compact["windows"]["1d"])

    def test_daily_brief_prefers_detail_links_and_splits_platform(self):
        reference_time = datetime.fromisoformat("2026-04-24T12:00:00+07:00")
        payload = {
            "date": "20260424",
            "run_date": "2026-04-24",
            "reference_time": reference_time.isoformat(),
            "items": [
                {
                    "topic": "sports",
                    "title": "中超关键赛果",
                    "source": "央视体育",
                    "url": "https://news.google.com/rss/articles/example",
                    "reference_url": "https://example.com/story",
                    "detail_url": "https://rdxw.cc/hot/sports/sports-1.html",
                    "total_score": 8.2,
                    "editorial_summary": "泰山与海港战平，后续争冠走势值得跟进。",
                },
                {
                    "topic": "platform",
                    "source_topic": "x",
                    "title": "OpenAI 官方发布新帖",
                    "source": "x.com",
                    "reference_url": "https://x.com/openai/status/1",
                    "detail_url": "https://rdxw.cc/hot/platform/platform-x.html",
                    "total_score": 7.8,
                },
                {
                    "topic": "platform",
                    "source_topic": "youtube",
                    "title": "OpenAI 官方视频更新",
                    "source": "YouTube",
                    "reference_url": "https://youtube.com/watch?v=1",
                    "detail_url": "https://rdxw.cc/hot/platform/platform-youtube.html",
                    "total_score": 7.6,
                },
            ],
        }
        brief = build_daily_brief_payload(payload, reference_time, per_section=2)
        sports_item = brief["sections"][0]["items"][0]
        self.assertEqual(sports_item["url"], "https://rdxw.cc/hot/sports/sports-1.html")
        self.assertEqual(sports_item["original_url"], "https://example.com/story")
        self.assertIn("creator_angle", sports_item)
        self.assertIn("editorial_value_score", sports_item)
        self.assertIn("publication_briefing", sports_item)
        self.assertIn("切口：", brief["text"])
        self.assertIn("价值：", brief["text"])
        self.assertNotIn("看点：24小时内仍在发酵", brief["text"])
        self.assertIn("详情：https://rdxw.cc/hot/sports/sports-1.html", brief["text"])
        self.assertIn("天气、黄历不由本站生成", brief["text"])
        self.assertIn("weather_almanac_policy", brief)
        sections = {section["key"]: section for section in brief["sections"]}
        self.assertEqual(sections["x"]["items"][0]["title"], "OpenAI 官方发布新帖")
        self.assertEqual(sections["youtube"]["items"][0]["title"], "OpenAI 官方视频更新")

    def test_daily_brief_creator_angle_does_not_match_generic_final_words(self):
        reference_time = datetime.fromisoformat("2026-04-24T12:00:00+07:00")
        payload = {
            "date": "20260424",
            "run_date": "2026-04-24",
            "reference_time": reference_time.isoformat(),
            "items": [
                {
                    "topic": "sports",
                    "title": "U17国足2-0澳大利亚晋级决赛",
                    "source": "央视体育",
                    "detail_url": "https://rdxw.cc/hot/sports/u17.html",
                    "total_score": 8.2,
                },
                {
                    "topic": "esports",
                    "title": "520是LPL的MSI幸运日？八年前RNG夺冠",
                    "source": "Zhibo8",
                    "detail_url": "https://rdxw.cc/hot/esports/lpl.html",
                    "total_score": 7.9,
                },
            ],
        }
        brief = build_daily_brief_payload(payload, reference_time, per_section=2)
        sections = {section["key"]: section for section in brief["sections"]}
        self.assertNotIn("阿森纳", sections["sports"]["items"][0]["creator_angle"])
        self.assertNotIn("个人选择", sections["esports"]["items"][0]["creator_angle"])

    def test_rss_exposes_feed_metadata_and_boundary_note(self):
        rss = runner.render_rss_feed(
            {
                "reference_time": "2026-04-24T12:00:00+07:00",
                "items": [
                    {
                        "topic": "sports",
                        "topic_label": "体育热点",
                        "title": "中超关键赛果",
                        "summary": "泰山与海港战平。",
                        "source": "央视体育",
                        "detail_url": "https://rdxw.cc/hot/sports/sports-1.html",
                        "published_at": "2026-04-24T10:00:00+08:00",
                    }
                ],
            }
        )
        self.assertIn('xmlns:atom="http://www.w3.org/2005/Atom"', rss)
        self.assertIn("<ttl>30</ttl>", rss)
        self.assertIn("天气和黄历由私域推送侧另行拼接", rss)

    def test_source_radar_item_is_normalized(self):
        source = {"id": "weibo", "label": "微博", "title": "实时热搜", "topic": "platform", "group": "平台热议"}
        item = normalize_source_radar_item(
            {
                "id": "hot-1",
                "title": "<b>辽宁丹东交通事故已致8人死亡</b>",
                "url": "/story",
                "extra": {"info": "504万", "hover": "微博热搜"},
            },
            source,
            1,
            {},
        )
        self.assertIsNotNone(item)
        self.assertEqual(item["title"], "辽宁丹东交通事故已致8人死亡")
        self.assertEqual(item["url"], "https://newsnow.busiyi.world/story")
        self.assertEqual(item["hot_value"], "504万")
        self.assertEqual(item["topic"], "platform")
        self.assertTrue(source_radar_timestamp(1777891990000).startswith("2026-05-04T"))
        self.assertIsNone(
            normalize_source_radar_item(
                {"title": '"IM电竞官方 85136.vipKpT" - Results on X｜直播 Posts & Updates'},
                source,
                1,
                {},
            )
        )

    def test_source_radar_sources_are_configurable(self):
        sources = load_source_radar_sources()
        self.assertGreaterEqual(len(sources), 10)
        first = sources[0]
        self.assertIn("column", first)
        self.assertIn("quality_tier", first)
        self.assertIn("focus_default", first)

    def test_source_radar_card_cache_roundtrip(self):
        old_cache_dir = runner.SOURCE_RADAR_CACHE_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.SOURCE_RADAR_CACHE_DIR = Path(tmpdir)
            card = {
                "id": "weibo",
                "label": "微博",
                "status": "success",
                "items": [{"rank": 1, "title": "热点"}],
            }
            write_cached_source_radar_card(card)
            cached = load_cached_source_radar_card("weibo")
            self.assertIsNotNone(cached)
            self.assertEqual(cached["status"], "cache")
            self.assertTrue(cached["cache_used"])
        runner.SOURCE_RADAR_CACHE_DIR = old_cache_dir

    def test_og_fallback_does_not_overwrite_existing_images_without_pillow(self):
        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ModuleNotFoundError("blocked PIL for fallback test")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "existing.png"
            existing.write_bytes(b"existing image bytes")
            missing = Path(tmpdir) / "missing.png"
            builtins.__import__ = blocked_import
            try:
                runner.write_og_card(existing, "title", "subtitle", "eyebrow", "metric")
                runner.write_og_card(missing, "title", "subtitle", "eyebrow", "metric")
            finally:
                builtins.__import__ = original_import
            self.assertEqual(existing.read_bytes(), b"existing image bytes")
            self.assertTrue(missing.exists())
            self.assertGreater(missing.stat().st_size, 100)

    def test_google_news_decoder_keeps_non_google_urls(self):
        self.assertEqual(decode_google_news_article_url("https://example.com/a"), "https://example.com/a")
        self.assertEqual(decode_google_news_article_url("https://news.google.com/rss/articles/not-base64?oc=5"), "")
        self.assertEqual(resolve_reference_url("https://example.com/a"), "https://example.com/a")

    def test_source_quality_tier_marks_trusted_sources(self):
        self.assertEqual(source_quality_tier({"source": "央视体育", "url": "https://sports.cctv.com/story"}), "high")
        self.assertEqual(source_quality_tier({"source": "手机新浪网", "url": "https://sports.sina.cn/story"}), "low")

    def test_static_site_outputs_include_real_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()
            ranked_payload = {
                "run_date": "2026-04-24",
                "reference_time": "2026-04-24T12:00:00+07:00",
                "items": [
                    {
                        "topic": "sports",
                        "topic_label": "体育热点",
                        "hotspot_id": "sports-strong",
                        "detail_path": "hot/sports/sports-strong.html",
                        "title": "中超关键赛果",
                        "summary": "泰山与海港战平。",
                        "source": "央视体育",
                        "url": "https://example.com/story",
                        "reference_url": "https://example.com/story",
                        "editorial_value_level": "强选题",
                        "editorial_value_score": 9.8,
                        "sources": [
                            {"source": "央视体育", "domain": "sports.cctv.com", "url": "https://sports.cctv.com"},
                            {"source": "虎扑", "domain": "bbs.hupu.com", "url": "https://bbs.hupu.com"},
                            {"source": "新华社", "domain": "xinhuanet.com", "url": "https://xinhuanet.com"},
                        ],
                    },
                    {
                        "topic": "sports",
                        "topic_label": "体育热点",
                        "hotspot_id": "sports-weak",
                        "detail_path": "hot/sports/sports-weak.html",
                        "title": "单来源普通热点",
                        "summary": "只有一个来源，保留站内浏览但不主动提交索引。",
                        "source": "普通来源",
                        "url": "https://example.com/weak",
                        "reference_url": "https://example.com/weak",
                        "sources": [{"source": "普通来源", "domain": "example.com", "url": "https://example.com/weak"}],
                    }
                ],
                "topic_labels": {
                    "sports": "体育热点",
                    "esports": "电竞热点",
                    "ai": "AI科技热点",
                    "entertainment": "泛娱乐热点",
                    "platform": "平台热议",
                    "github": "GitHub热点项目",
                },
            }
            windows_payload = {
                "generated_at": "2026-04-24T12:00:00+07:00",
                "available_windows": [
                    {"key": "1d", "label": "24小时", "days": 1},
                    {"key": "3d", "label": "3天", "days": 3},
                    {"key": "7d", "label": "7天", "days": 7},
                ],
                "windows": {
                    "1d": {"topic_counts": {"sports": 1}, "items": ranked_payload["items"] + [
                        {
                            "topic": "sports",
                            "topic_label": "体育热点",
                            "hotspot_id": "sports-window-only",
                            "detail_path": "hot/sports/sports-window-only.html",
                            "title": "窗口强信号但未进主榜",
                            "summary": "窗口页可点击，但不应主动提交搜索索引。",
                            "source": "窗口来源",
                            "url": "https://example.com/window-only",
                            "reference_url": "https://example.com/window-only",
                            "editorial_value_level": "强选题",
                            "editorial_value_score": 9.5,
                            "sources": [
                                {"source": "来源一", "domain": "one.example", "url": "https://one.example"},
                                {"source": "来源二", "domain": "two.example", "url": "https://two.example"},
                            ],
                        }
                    ]},
                    "3d": {"topic_counts": {"sports": 1}, "items": ranked_payload["items"]},
                    "7d": {"topic_counts": {"sports": 1}, "items": ranked_payload["items"]},
                },
            }
            manifest_path = write_split_topic_payloads(output_dir, ranked_payload, windows_payload)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            site_root = output_dir.parent
            retained_old = site_root / "hot" / "sports" / "retained.html"
            expired_old = site_root / "hot" / "sports" / "expired.html"
            noisy_old = site_root / "hot" / "platform" / "noisy.html"
            legacy_daily = site_root / "daily" / "2026-04-22.html"
            appledouble_daily = site_root / "daily" / "._2026-04-23.html"
            retained_old.parent.mkdir(parents=True, exist_ok=True)
            noisy_old.parent.mkdir(parents=True, exist_ok=True)
            appledouble_daily.parent.mkdir(parents=True, exist_ok=True)
            retained_old.write_text("retained", encoding="utf-8")
            expired_old.write_text("expired", encoding="utf-8")
            noisy_old.write_text("<h1>Maa Inti Devatha Official Promo | Telugu Serial</h1>", encoding="utf-8")
            legacy_daily.write_text(
                """<!doctype html>
<html lang="zh-CN">
<head>
  <title>2026-04-22 热点日报 | RDXW 热点雷达</title>
  <meta name="description" content="旧描述" />
  <link rel="canonical" href="https://rdxw.cc/daily/2026-04-22.html" />
</head>
<body><p class="desc">2026-04-22 多频道热点日报，共 1 条。</p></body>
</html>""",
                encoding="utf-8",
            )
            appledouble_daily.write_text("AppleDouble metadata", encoding="utf-8")
            retained_ts = datetime.fromisoformat("2026-04-20T12:00:00+07:00").timestamp()
            expired_ts = datetime.fromisoformat("2026-03-01T12:00:00+07:00").timestamp()
            os.utime(retained_old, (retained_ts, retained_ts))
            os.utime(expired_old, (expired_ts, expired_ts))
            os.utime(noisy_old, (retained_ts, retained_ts))
            result = write_static_site_outputs(output_dir, ranked_payload, windows_payload, manifest)
            self.assertGreater(result["count"], 0)
            self.assertEqual(result["removed_appledouble_artifacts"], 1)
            self.assertGreaterEqual(result["refreshed_daily_meta"], 1)
            self.assertEqual(result["daily_longtail_page"], "daily/2026-04-24-longtail.html")
            self.assertGreaterEqual(result["daily_longtail_items"], 1)
            self.assertEqual(result["keyword_hub_page"], "hotspot-keywords.html")
            self.assertEqual(result["heat_index_page"], "heat-index.html")
            self.assertGreaterEqual(result["heat_index_items"], 2)
            self.assertGreaterEqual(result["interpretation_candidate_items"], 1)
            self.assertEqual(result["sports_profile_hub_page"], "sports-profiles.html")
            self.assertEqual(result["world_cup_recommendation_page"], "world-cup-recommendations.html")
            self.assertGreaterEqual(result["sports_profile_pages"], 70)
            self.assertGreaterEqual(result["sports_profile_keyword_items"], 70)
            self.assertFalse(appledouble_daily.exists())
            self.assertEqual(result["retained_old_details"], 1)
            self.assertTrue(retained_old.exists())
            self.assertFalse(expired_old.exists())
            self.assertFalse(noisy_old.exists())
            self.assertIn("中超关键赛果", (site_root / "sports.html").read_text(encoding="utf-8"))
            self.assertIn("中超关键赛果", (site_root / "feed.xml").read_text(encoding="utf-8"))
            self.assertTrue(any((site_root / "hot" / "sports").glob("*.html")))
            self.assertIn("sitemap-hot.xml", (site_root / "sitemap.xml").read_text(encoding="utf-8"))
            legacy_daily_html = legacy_daily.read_text(encoding="utf-8")
            self.assertIn('property="og:title"', legacy_daily_html)
            self.assertIn('name="twitter:card" content="summary_large_image"', legacy_daily_html)
            self.assertNotIn("._2026-04-23.html", (site_root / "sitemap-daily.xml").read_text(encoding="utf-8"))
            sitemap_hot = (site_root / "sitemap-hot.xml").read_text(encoding="utf-8")
            self.assertIn("/hot/sports/sports-strong.html", sitemap_hot)
            self.assertNotIn("/hot/sports/sports-weak.html", sitemap_hot)
            self.assertNotIn("/hot/sports/sports-window-only.html", sitemap_hot)
            self.assertIn('name="robots" content="noindex,follow"', (site_root / "hot" / "sports" / "sports-weak.html").read_text(encoding="utf-8"))
            self.assertIn('name="robots" content="noindex,follow"', (site_root / "hot" / "sports" / "sports-window-only.html").read_text(encoding="utf-8"))
            self.assertEqual(result["indexable_hot_details"], 1)
            self.assertIn("sports.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("global-hot.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("hotspot-keywords.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("heat-index.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("world-cup-recommendations.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("trend-sources.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("methodology.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("weekly/index.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("api.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("daily/2026-04-24-longtail.html", (site_root / "sitemap-daily.xml").read_text(encoding="utf-8"))
            self.assertNotIn("feed.xml", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertNotIn("llms.txt", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertNotIn("ai-context.txt", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertTrue((site_root / "search-console-priority-urls.txt").exists())
            self.assertTrue((site_root / "llms.txt").exists())
            self.assertTrue((site_root / "home.html").exists())
            self.assertTrue((site_root / "global-hot.html").exists())
            self.assertTrue((site_root / "ai-context.txt").exists())
            self.assertTrue((site_root / "robots.txt").exists())
            self.assertTrue((site_root / "assets" / "og" / "rdxw-logo.png").exists())
            self.assertTrue((site_root / "indexnow-key.txt").exists())
            self.assertRegex((site_root / "indexnow-key.txt").read_text(encoding="utf-8").strip(), r"^[A-Za-z0-9-]{8,128}$")
            self.assertTrue((site_root / "methodology.html").exists())
            self.assertTrue((site_root / "weekly" / "index.html").exists())
            self.assertTrue((site_root / "trend-sources.html").exists())
            self.assertTrue((site_root / "api.html").exists())
            self.assertTrue((site_root / "feedback.html").exists())
            self.assertTrue((site_root / "heat-index.html").exists())
            self.assertTrue((site_root / "editorial-briefs.html").exists())
            self.assertTrue((site_root / "hotspot-keywords.html").exists())
            self.assertTrue((site_root / "sports-profiles.html").exists())
            self.assertTrue((site_root / "world-cup-recommendations.html").exists())
            self.assertTrue((site_root / "sports-profiles" / "mexico-national-team.html").exists())
            self.assertTrue((site_root / "sports-profiles" / "united-states-national-team.html").exists())
            self.assertTrue((site_root / "sports-profiles" / "japan-national-team.html").exists())
            self.assertTrue((site_root / "sports-profiles" / "croatia-national-team.html").exists())
            self.assertTrue((site_root / "sports-profiles" / "ghana-national-team.html").exists())
            self.assertTrue((site_root / "sports-profiles" / "son-heung-min.html").exists())
            self.assertTrue((site_root / "daily" / "2026-04-24-longtail.html").exists())
            self.assertTrue((output_dir / "latest_longtail_keywords.json").exists())
            self.assertTrue((output_dir / "heat-index.json").exists())
            self.assertTrue((output_dir / "interpretation_candidates.json").exists())
            self.assertTrue((output_dir / "editorial_brief_candidates.json").exists())
            self.assertTrue((output_dir / "sports_profile_keywords.json").exists())
            heat_payload = json.loads((output_dir / "heat-index.json").read_text(encoding="utf-8"))
            self.assertEqual(heat_payload["version"], "heat-score-v1")
            self.assertGreaterEqual(len(heat_payload["items"]), 2)
            self.assertIn("heat_score", heat_payload["items"][0])
            self.assertIn("velocity_score", heat_payload["items"][0])
            self.assertIn("source_diversity_score", heat_payload["items"][0])
            candidates_payload = json.loads((output_dir / "interpretation_candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(candidates_payload["default_robots"], "noindex,follow")
            self.assertTrue(candidates_payload["items"][0]["review_required"])
            self.assertIn("draft_title", candidates_payload["items"][0])
            self.assertIn("manual_review_checklist", candidates_payload["items"][0])
            editorial_payload = json.loads((output_dir / "editorial_brief_candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(editorial_payload["version"], "interpretation-candidates-v1")
            editorial_html = (site_root / "editorial-briefs.html").read_text(encoding="utf-8")
            self.assertIn('name="robots" content="noindex,follow"', editorial_html)
            self.assertIn("今日深挖候选", editorial_html)
            self.assertIn("发布前检查", editorial_html)
            self.assertNotIn("editorial-briefs.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            feedback_html = (site_root / "feedback.html").read_text(encoding="utf-8")
            self.assertIn('name="robots" content="noindex,follow"', feedback_html)
            self.assertIn("/api/feedback", feedback_html)
            self.assertIn("提交反馈", feedback_html)
            self.assertNotIn("feedback.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            index_html = (site_root / "index.html").read_text(encoding="utf-8")
            self.assertIn('"@type":"Organization"', index_html)
            self.assertIn('"@type":"WebPage"', index_html)
            self.assertIn('"@graph"', index_html)
            self.assertIn("rdxw-logo.png", index_html)
            self.assertIn("assets/og/rdxw-home.png", index_html)
            self.assertIn(f'<img src="/assets/og/rdxw-home.png?v={runner.IMAGE_ASSET_VERSION}"', index_html)
            self.assertIn("热度指数", index_html)
            self.assertIn("热榜源导航", index_html)
            self.assertIn("热点词库", index_html)
            self.assertNotIn("晋级线清楚，下一轮话题还能再拉开", index_html)
            self.assertNotIn("球队球星资料卡", index_html)
            profile_hub_html = (site_root / "sports-profiles.html").read_text(encoding="utf-8")
            self.assertIn("球队球星资料卡", profile_hub_html)
            self.assertNotIn("sponsor-section", index_html)
            self.assertNotIn("floating-ad", index_html)
            self.assertNotIn("x851.cc", index_html)
            heat_html = (site_root / "heat-index.html").read_text(encoding="utf-8")
            self.assertIn("RDXW 热度指数", heat_html)
            self.assertIn("heat_score_v1", heat_html)
            self.assertIn('"@type":"Dataset"', heat_html)
            self.assertIn("今日深挖候选", heat_html)
            self.assertIn("sports-match-center.html", heat_html)
            source_html = (site_root / "trend-sources.html").read_text(encoding="utf-8")
            self.assertIn("热点源导航", source_html)
            self.assertIn("Source Radar", source_html)
            self.assertIn("assets/og/rdxw-trend-sources.png", source_html)
            self.assertIn(f'<img src="/assets/og/rdxw-trend-sources.png?v={runner.IMAGE_ASSET_VERSION}"', source_html)
            self.assertTrue((site_root / "embed" / "latest.html").exists())
            self.assertTrue((site_root / "topics" / "index.html").exists())
            self.assertTrue((site_root / "topics" / "zhongchao-hot.html").exists())
            detail_html = next(
                p.read_text(encoding="utf-8")
                for p in sorted((site_root / "hot" / "sports").glob("*.html"))
                if p.name != "retained.html"
            )
            self.assertIn('"@graph"', detail_html)
            self.assertIn("为什么值得关注", detail_html)
            self.assertIn("多平台讨论焦点", detail_html)
            self.assertIn("后续影响与相关搜索", detail_html)
            self.assertIn("不同读者怎么看", detail_html)
            self.assertIn("阅读提醒", detail_html)
            self.assertIn("相关搜索与长尾词", detail_html)
            self.assertIn("中超关键赛果 为什么", detail_html)
            self.assertIn("RDXW 核对依据与更新说明", detail_html)
            self.assertIn("assets/og/rdxw-sports.png", detail_html)
            self.assertIn(f'<img src="/assets/og/rdxw-sports.png?v={runner.IMAGE_ASSET_VERSION}"', detail_html)
            self.assertIn("继续看相关专题", detail_html)
            self.assertIn("/topics/zhongchao-hot.html", detail_html)
            cluster_html = (site_root / "topics" / "zhongchao-hot.html").read_text(encoding="utf-8")
            self.assertIn("相关搜索入口", cluster_html)
            self.assertIn("中超热点最新", cluster_html)
            self.assertIn("承接搜索词", (site_root / "topics" / "index.html").read_text(encoding="utf-8"))
            longtail_html = (site_root / "daily" / "2026-04-24-longtail.html").read_text(encoding="utf-8")
            self.assertIn("今日热点长尾词", longtail_html)
            self.assertIn("中超关键赛果 是什么情况", longtail_html)
            keyword_hub_html = (site_root / "hotspot-keywords.html").read_text(encoding="utf-8")
            self.assertIn("热点搜索词库", keyword_hub_html)
            self.assertIn("中超关键赛果 是什么情况", keyword_hub_html)
            self.assertIn("今日高频词组", keyword_hub_html)
            self.assertIn("球队球星长尾词", keyword_hub_html)
            self.assertIn("墨西哥国家队", keyword_hub_html)
            sports_profile_html = (site_root / "sports-profiles" / "mexico-national-team.html").read_text(encoding="utf-8")
            self.assertIn("墨西哥 2-0 南非", sports_profile_html)
            self.assertIn("世界杯揭幕战", sports_profile_html)
            self.assertIn('"@type":"ProfilePage"', sports_profile_html)
            world_cup_html = (site_root / "world-cup-recommendations.html").read_text(encoding="utf-8")
            self.assertIn("世界杯资料卡推荐", world_cup_html)
            self.assertIn("今日优先关注", world_cup_html)
            self.assertIn("按小组看球队资料卡", world_cup_html)
            self.assertIn("不是投注预测", world_cup_html)
            self.assertIn("美国国家队", world_cup_html)
            self.assertIn("孙兴慜", world_cup_html)
            self.assertIn("世界杯页面继续看", world_cup_html)
            self.assertIn("sports-profiles/mexico-national-team.html", (site_root / "sitemap-topics.xml").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles/united-states-national-team.html", (site_root / "sitemap-topics.xml").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles/japan-national-team.html", (site_root / "sitemap-topics.xml").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles/son-heung-min.html", (site_root / "sitemap-topics.xml").read_text(encoding="utf-8"))
            self.assertIn("hotspot-keywords.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("global-hot.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("heat-index.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("world-cup-recommendations.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles/mexico-national-team.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles/son-heung-min.html", (site_root / "search-console-priority-urls.txt").read_text(encoding="utf-8"))
            self.assertIn("hotspot-keywords.html", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("global-hot.html", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("heat-index.html", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("world-cup-recommendations.html", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles.html", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("GEO / AI 搜索引用建议", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("最新人工深挖页", (site_root / "llms.txt").read_text(encoding="utf-8"))
            self.assertIn("hotspot-keywords.html", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            self.assertIn("global-hot.html", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            self.assertIn("heat-index.html", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            self.assertIn("world-cup-recommendations.html", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            self.assertIn("sports-profiles.html", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            self.assertIn("GEO / AI 搜索引用方式", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            self.assertIn("最新人工深挖页", (site_root / "ai-context.txt").read_text(encoding="utf-8"))
            robots_txt = (site_root / "robots.txt").read_text(encoding="utf-8")
            self.assertIn("GPTBot", robots_txt)
            self.assertIn("OAI-SearchBot", robots_txt)
            self.assertIn("ClaudeBot", robots_txt)
            self.assertIn("PerplexityBot", robots_txt)
            self.assertIn("site.webmanifest", (site_root / "sports.html").read_text(encoding="utf-8"))

    def test_manual_analysis_page_has_geo_citable_blocks(self):
        html = runner.render_manual_analysis_page(
            {
                "title": "豆包千问下线智能体功能，普通用户要备份什么？",
                "description": "豆包和千问调整智能体功能，用户需要确认历史配置和自动化入口是否还可用。",
                "summary": "多个 AI 产品调整智能体能力，普通用户最先需要确认自己保存的工作流、提示词和外部入口是否受影响。",
                "topic": "ai",
                "topic_label": "AI热点",
                "published_at": "2026-07-05T10:00:00+08:00",
                "heat_score": 8.6,
                "velocity_score": 7.2,
                "source_count": 4,
                "keywords": ["豆包智能体", "千问智能体", "AI热点"],
                "sections": [
                    {
                        "heading": "发生了什么",
                        "paragraphs": ["多个 AI 产品调整智能体能力，用户需要确认功能入口、历史工作流和外部调用是否仍然可用。"],
                    }
                ],
            },
            {"generated_at": "2026-07-05T10:00:00+08:00"},
        )
        self.assertIn("AI 可引用摘要", html)
        self.assertIn("这条热点一句话看懂", html)
        self.assertIn("常见问题", html)
        self.assertIn('"@type":"FAQPage"', html)
        self.assertIn("为什么这条热点今天升温？", html)

    def test_item_longtail_generation_uses_title_topic_and_followup_intent(self):
        item = {
            "topic": "sports",
            "topic_label": "体育热点",
            "title": "英超落下帷幕后过人榜正式出炉",
            "summary": "英超赛季结束，过人榜公布。",
            "source": "虎扑",
            "entity_tags": ["英超", "过人榜"],
            "keyword_hits": ["赛季"],
            "total_score": 8.8,
        }
        enrich_item_for_publication(item)
        longtail = build_item_longtail(item)
        self.assertIn("英超落下帷幕后过人榜正式出炉 为什么", longtail["keywords"])
        self.assertIn("英超落下帷幕后过人榜正式出炉 后续有哪些看点", longtail["questions"])
        self.assertIn("英超", item["longtail_keywords"])
        self.assertTrue(any(row["intent"] == "事实核对" for row in item["search_intents"]))

    def test_llm_editorial_patch_overrides_publication_fields(self):
        item = {
            "topic": "sports",
            "topic_label": "体育热点",
            "title": "中超蓉城绝杀收获七连胜",
            "summary": "蓉城绝杀取胜。",
            "source": "央视体育",
            "url": "https://example.com/story",
            "total_score": 8.1,
        }
        apply_llm_editorial_patch(
            item,
            {
                "editorial_summary": "蓉城靠补时绝杀延续连胜，争冠讨论会继续升温。",
                "creator_angle": "从绝杀球和七连胜切入，拆蓉城为什么进入争冠叙事。",
                "why_it_matters": "中超强队主线明确，后续赛程和球迷情绪都有延展空间。",
                "what_to_watch_next": "看下一轮对阵、伤停和主帅赛后表态。",
                "controversy_point": "暂时无强争议，重点看球迷对争冠成色的分歧。",
                "editorial_value_score": 9.2,
                "editorial_value_level": "强选题",
                "editorial_value_reason": "强赛果加持续主线。",
                "seo_keywords": ["中超热点", "蓉城", "七连胜"],
            },
            model="test-model",
        )
        enrich_item_for_publication(item)
        self.assertEqual(item["editorial_value_score"], 9.2)
        self.assertEqual(item["editorial_value_level"], "强选题")
        self.assertEqual(item["publication_briefing"]["why_it_matters"], "中超强队主线明确，后续赛程和球迷情绪都有延展空间。")
        self.assertIn("中超热点", item["seo_keywords"])

    def test_seo_cluster_pages_collect_matching_items(self):
        ranked_payload = {
            "run_date": "2026-04-24",
            "items": [
                {
                    "topic": "sports",
                    "topic_label": "体育热点",
                    "title": "中超蓉城绝杀收获七连胜",
                    "summary": "蓉城赢球。",
                    "source": "央视体育",
                    "url": "https://example.com/sports",
                    "total_score": 8.3,
                },
                {
                    "topic": "esports",
                    "topic_label": "电竞热点",
                    "title": "LPL 转会窗口战队阵容调整",
                    "summary": "战队阵容变化。",
                    "source": "5EPlay",
                    "url": "https://example.com/esports",
                    "total_score": 8.0,
                },
            ],
        }
        windows_payload = {"windows": {"7d": {"items": ranked_payload["items"]}}}
        pages = build_seo_cluster_pages(ranked_payload, windows_payload)
        paths = {page["path"] for page in pages}
        self.assertIn("topics/zhongchao-hot.html", paths)
        self.assertIn("topics/esports-transfer-hot.html", paths)

    def test_semantic_merge_ranked_items_keeps_best_and_merges_sources(self):
        reference_time = datetime.fromisoformat("2026-04-24T12:00:00+07:00")
        items = [
            {
                "topic": "sports",
                "topic_label": "体育热点",
                "title": "泰山1-0海港晋级",
                "summary": "泰山晋级。",
                "source": "央视体育",
                "url": "https://example.com/a",
                "reference_url": "https://example.com/a",
                "total_score": 7.2,
                "event_key": "sports:泰山|海港|晋级",
                "sources": [{"source": "央视体育", "title": "泰山晋级", "url": "https://example.com/a"}],
            },
            {
                "topic": "sports",
                "topic_label": "体育热点",
                "title": "山东泰山击败上海海港晋级",
                "summary": "山东泰山晋级。",
                "source": "新华社",
                "url": "https://example.com/b",
                "reference_url": "https://example.com/b",
                "total_score": 8.1,
                "event_key": "sports:泰山|海港|晋级",
                "sources": [{"source": "新华社", "title": "山东泰山晋级", "url": "https://example.com/b"}],
            },
        ]
        merged = semantic_merge_ranked_items(items, reference_time, top=10)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "新华社")
        self.assertEqual(merged[0]["source_count"], 2)
        self.assertIn("publication_briefing", merged[0])

    def test_source_quality_payload_tracks_selected_sources(self):
        ranked_payload = {
            "items": [
                {
                    "topic": "sports",
                    "title": "中超关键赛果",
                    "source": "央视体育",
                    "score": 8.2,
                    "sources": [{"source": "央视体育", "domain": "sports.cctv.com"}],
                }
            ]
        }
        windows_payload = {"windows": {"7d": {"items": ranked_payload["items"]}}}
        payload = build_source_quality_payload(
            ranked_payload,
            windows_payload,
            {"sources": [{"label": "微博", "status": "success", "item_count": 20, "items": [{"title": "热搜"}]}]},
            datetime.fromisoformat("2026-04-24T12:00:00+07:00"),
        )
        source_names = {row["source"] for row in payload["sources"]}
        self.assertIn("央视体育", source_names)
        self.assertIn("微博", source_names)

    def test_health_payload_reports_core_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()
            (output_dir / "latest_daily_brief.json").write_text("{}", encoding="utf-8")
            (output_dir / "latest_hotspots_manifest.json").write_text("{}", encoding="utf-8")
            payload = build_health_payload(
                output_dir,
                {"items": [{"title": "a"}]},
                {"run_date": "2026-04-24", "topic_counts": {"sports": 1}, "items": [{"topic": "sports"}]},
                {"windows": {"7d": {"items": [{"topic": "sports"}]}}},
                [{"topic": "sports", "name": "sports", "count": 1}],
                {"sources": [{"label": "微博", "items": [{"title": "a"}]}]},
                {"count": 3},
                datetime.fromisoformat("2026-04-24T12:00:00+07:00"),
            )
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["raw_total"], 1)
            self.assertEqual(payload["window_counts"]["7d"], 1)

    def test_known_llm_region_error_does_not_warn_health(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()
            (output_dir / "latest_daily_brief.json").write_text("{}", encoding="utf-8")
            (output_dir / "latest_hotspots_manifest.json").write_text("{}", encoding="utf-8")
            (output_dir / "llm_editorial_status.json").write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "live_enabled": True,
                        "model": "gpt-5.5",
                        "applied": 7,
                        "errors": [
                            "OpenAI API HTTP 403 | code=unsupported_country_region_territory | Country, region, or territory not supported"
                        ],
                        "degraded_reason": "openai_unsupported_country_region_territory",
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(llm_error_is_known_non_core("code=unsupported_country_region_territory"))
            payload = build_health_payload(
                output_dir,
                {"items": [{"title": "a"}]},
                {"run_date": "2026-04-24", "topic_counts": {topic: 1 for topic in runner.ALL_TOPICS}, "items": [{"topic": "sports"}]},
                {"windows": {"7d": {"items": [{"topic": "sports"}]}}},
                [{"topic": "sports", "name": "sports", "count": 1}],
                {"sources": [{"label": "微博", "items": [{"title": "a"}]}]},
                {"count": 3},
                datetime.fromisoformat("2026-04-24T12:00:00+07:00"),
            )
            self.assertNotIn("LLM 编辑层有部分请求失败", payload["warnings"])
            self.assertEqual(payload["llm_editorial"]["degraded_reason"], "openai_unsupported_country_region_territory")


if __name__ == "__main__":
    unittest.main()
