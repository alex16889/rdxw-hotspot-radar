import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import run_daily_hotspots as runner
from run_daily_hotspots import (
    apply_llm_editorial_patch,
    build_daily_brief_payload,
    build_seo_cluster_pages,
    build_window_items,
    build_source_quality_payload,
    compact_window_payload,
    decode_google_news_article_url,
    enrich_item_for_publication,
    build_health_payload,
    is_spam_or_ad_title,
    llm_error_is_known_non_core,
    load_source_radar_sources,
    load_cached_source_radar_card,
    low_value_item_title,
    normalize_source_radar_item,
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
            retained_old.parent.mkdir(parents=True, exist_ok=True)
            noisy_old.parent.mkdir(parents=True, exist_ok=True)
            retained_old.write_text("retained", encoding="utf-8")
            expired_old.write_text("expired", encoding="utf-8")
            noisy_old.write_text("<h1>Maa Inti Devatha Official Promo | Telugu Serial</h1>", encoding="utf-8")
            retained_ts = datetime.fromisoformat("2026-04-20T12:00:00+07:00").timestamp()
            expired_ts = datetime.fromisoformat("2026-03-01T12:00:00+07:00").timestamp()
            os.utime(retained_old, (retained_ts, retained_ts))
            os.utime(expired_old, (expired_ts, expired_ts))
            os.utime(noisy_old, (retained_ts, retained_ts))
            result = write_static_site_outputs(output_dir, ranked_payload, windows_payload, manifest)
            self.assertGreater(result["count"], 0)
            self.assertEqual(result["retained_old_details"], 1)
            self.assertTrue(retained_old.exists())
            self.assertFalse(expired_old.exists())
            self.assertFalse(noisy_old.exists())
            self.assertIn("中超关键赛果", (site_root / "sports.html").read_text(encoding="utf-8"))
            self.assertIn("中超关键赛果", (site_root / "feed.xml").read_text(encoding="utf-8"))
            self.assertTrue(any((site_root / "hot" / "sports").glob("*.html")))
            self.assertIn("sitemap-hot.xml", (site_root / "sitemap.xml").read_text(encoding="utf-8"))
            sitemap_hot = (site_root / "sitemap-hot.xml").read_text(encoding="utf-8")
            self.assertIn("/hot/sports/sports-strong.html", sitemap_hot)
            self.assertNotIn("/hot/sports/sports-weak.html", sitemap_hot)
            self.assertNotIn("/hot/sports/sports-window-only.html", sitemap_hot)
            self.assertIn('name="robots" content="noindex,follow"', (site_root / "hot" / "sports" / "sports-weak.html").read_text(encoding="utf-8"))
            self.assertIn('name="robots" content="noindex,follow"', (site_root / "hot" / "sports" / "sports-window-only.html").read_text(encoding="utf-8"))
            self.assertEqual(result["indexable_hot_details"], 1)
            self.assertIn("sports.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("methodology.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("weekly/index.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertIn("api.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertNotIn("feed.xml", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertNotIn("llms.txt", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertNotIn("ai-context.txt", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            self.assertTrue((site_root / "search-console-priority-urls.txt").exists())
            self.assertTrue((site_root / "llms.txt").exists())
            self.assertTrue((site_root / "home.html").exists())
            self.assertTrue((site_root / "ai-context.txt").exists())
            self.assertTrue((site_root / "indexnow-key.txt").exists())
            self.assertRegex((site_root / "indexnow-key.txt").read_text(encoding="utf-8").strip(), r"^[A-Za-z0-9-]{8,128}$")
            self.assertTrue((site_root / "methodology.html").exists())
            self.assertTrue((site_root / "weekly" / "index.html").exists())
            self.assertTrue((site_root / "api.html").exists())
            self.assertTrue((site_root / "feedback.html").exists())
            feedback_html = (site_root / "feedback.html").read_text(encoding="utf-8")
            self.assertIn('name="robots" content="noindex,follow"', feedback_html)
            self.assertIn("/api/feedback", feedback_html)
            self.assertIn("提交反馈", feedback_html)
            self.assertNotIn("feedback.html", (site_root / "sitemap-core.xml").read_text(encoding="utf-8"))
            index_html = (site_root / "index.html").read_text(encoding="utf-8")
            self.assertIn('"@type":"Organization"', index_html)
            self.assertIn('"@type":"WebPage"', index_html)
            self.assertTrue((site_root / "embed" / "latest.html").exists())
            self.assertTrue((site_root / "topics" / "index.html").exists())
            self.assertTrue((site_root / "topics" / "zhongchao-hot.html").exists())
            detail_html = next(
                p.read_text(encoding="utf-8")
                for p in sorted((site_root / "hot" / "sports").glob("*.html"))
                if p.name != "retained.html"
            )
            self.assertIn("继续看相关专题", detail_html)
            self.assertIn("/topics/zhongchao-hot.html", detail_html)
            cluster_html = (site_root / "topics" / "zhongchao-hot.html").read_text(encoding="utf-8")
            self.assertIn("相关搜索入口", cluster_html)
            self.assertIn("中超热点最新", cluster_html)
            self.assertIn("承接搜索词", (site_root / "topics" / "index.html").read_text(encoding="utf-8"))
            self.assertIn("site.webmanifest", (site_root / "sports.html").read_text(encoding="utf-8"))

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
