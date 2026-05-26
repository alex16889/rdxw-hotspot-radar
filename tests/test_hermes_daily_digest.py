import unittest
from datetime import datetime

from scripts.send_hermes_daily_digest import build_digest_payload, should_send_digest


class HermesDailyDigestTests(unittest.TestCase):
    def sample_brief(self):
        return {
            "date": "20260526",
            "run_date": "2026-05-26",
            "reference_time": "2026-05-26T08:12:00+07:00",
            "site_url": "https://rdxw.cc",
            "sections": [
                {
                    "key": "sports",
                    "label": "体育",
                    "items": [
                        {
                            "title": "中超关键赛果形成争冠主线",
                            "source": "央视体育",
                            "score": 8.6,
                            "summary": "赛果已经形成明确主线，适合做赛后复盘。",
                            "creator_angle": "切口：抓比分转折、关键球员和下一场对阵。",
                            "url": "https://rdxw.cc/hot/sports/a.html",
                        },
                        {
                            "title": "法网资格赛中国选手晋级",
                            "source": "央视体育",
                            "score": 7.8,
                        },
                    ],
                },
                {
                    "key": "ai",
                    "label": "AI",
                    "items": [
                        {
                            "title": "AI Agent 耳机发布",
                            "source": "新华网",
                            "score": 8.3,
                            "summary": "先看产品落地，再判断题材热度。",
                            "creator_angle": "切口：重点看智能体能替人做什么。",
                            "url": "https://rdxw.cc/hot/ai/a.html",
                        }
                    ],
                },
            ],
        }

    def test_digest_payload_is_concise_and_private_push_ready(self):
        payload = build_digest_payload(
            self.sample_brief(),
            {
                "source_count": 12,
                "ok_count": 12,
                "sources": [
                    {"id": "weibo", "label": "微博", "status": "success"},
                    {"id": "douyin", "label": "抖音", "status": "cache"},
                ],
            },
            {"ok": True, "ranked_total": 88, "warnings": [], "site_url": "https://rdxw.cc"},
            now=datetime.fromisoformat("2026-05-26T09:00:00"),
        )
        text = payload["text"]
        self.assertIn("RDXW 每日简报｜2026-05-26", text)
        self.assertIn("今日先看", text)
        self.assertIn("备选池", text)
        self.assertIn("来源雷达", text)
        self.assertIn("详情：https://rdxw.cc/hot/sports/a.html", text)
        self.assertLess(len(text), 3900)

    def test_send_gate_allows_once_per_day_after_min_hour(self):
        payload = {"date": "2026-05-26"}
        now = datetime.fromisoformat("2026-05-26T09:00:00")
        self.assertEqual(should_send_digest(payload, {}, now, 8, False), (True, "ready"))
        self.assertEqual(
            should_send_digest(payload, {"last_sent_date": "2026-05-26"}, now, 8, False),
            (False, "already_sent_today"),
        )
        early = datetime.fromisoformat("2026-05-26T07:00:00")
        self.assertEqual(should_send_digest(payload, {}, early, 8, False), (False, "before_min_hour:7<8"))
        self.assertEqual(should_send_digest(payload, {"last_sent_date": "2026-05-26"}, early, 8, True), (True, "force"))


if __name__ == "__main__":
    unittest.main()
