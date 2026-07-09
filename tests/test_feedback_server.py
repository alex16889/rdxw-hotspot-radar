import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "feedback_server.py"
SPEC = importlib.util.spec_from_file_location("feedback_server", MODULE_PATH)
feedback_server = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(feedback_server)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FeedbackNotificationTests(unittest.TestCase):
    def test_notification_text_is_short_and_actionable(self):
        entry = {
            "created_at": "2026-05-24T05:10:00+00:00",
            "type": "功能建议",
            "url": "https://rdxw.cc/feedback.html",
            "message": "希望增加篮球和足球分开的热点入口。",
            "contact": "",
        }
        text = feedback_server.build_feedback_notification(entry)
        self.assertIn("RDXW 新反馈", text)
        self.assertIn("类型：功能建议", text)
        self.assertIn("联系方式：未填", text)
        self.assertIn("篮球和足球", text)

    def test_send_feedback_notification_uses_hermes_channel_env(self):
        entry = {
            "created_at": "2026-05-24T05:10:00+00:00",
            "type": "Bug",
            "url": "https://rdxw.cc/sports.html",
            "message": "点击频道后页面没有明显提示。",
            "contact": "tester",
        }
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch.dict(
            os.environ,
            {
                "HOTSPOT_FEEDBACK_TELEGRAM_BOT_TOKEN": "test-token",
                "HOTSPOT_FEEDBACK_TELEGRAM_CHAT_ID": "test-chat",
                "HOTSPOT_FEEDBACK_NOTIFY_TIMEOUT": "1",
            },
            clear=True,
        ), patch.object(feedback_server, "urlopen", fake_urlopen):
            feedback_server.send_feedback_notification(entry)

        self.assertEqual(captured["url"], "https://api.telegram.org/bottest-token/sendMessage")
        self.assertEqual(captured["timeout"], 1.0)
        self.assertEqual(captured["payload"]["chat_id"], "test-chat")
        self.assertIn("RDXW 新反馈", captured["payload"]["text"])
        self.assertTrue(captured["payload"]["disable_web_page_preview"])


if __name__ == "__main__":
    unittest.main()
