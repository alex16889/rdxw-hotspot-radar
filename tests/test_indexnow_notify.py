import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "indexnow_notify.py"
SPEC = importlib.util.spec_from_file_location("indexnow_notify", MODULE_PATH)
indexnow_notify = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(indexnow_notify)


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class IndexNowNotifyTests(unittest.TestCase):
    def test_sitemap_index_and_due_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "indexnow-key.txt").write_text("abc12345\n", encoding="utf-8")
            (root / "index.html").write_text("home", encoding="utf-8")
            (root / "sports.html").write_text("sports", encoding="utf-8")
            (root / "sitemap.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://rdxw.cc/sitemap-core.xml</loc></sitemap>
</sitemapindex>""",
                encoding="utf-8",
            )
            (root / "sitemap-core.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://rdxw.cc/</loc></url>
  <url><loc>https://rdxw.cc/sports.html</loc></url>
  <url><loc>https://other.example/page.html</loc></url>
</urlset>""",
                encoding="utf-8",
            )
            urls = indexnow_notify.sitemap_urls(root, root / "sitemap.xml")
            self.assertEqual(urls, ["https://rdxw.cc/", "https://rdxw.cc/sports.html", "https://other.example/page.html"])
            candidates, state = indexnow_notify.due_urls(root, "https://rdxw.cc", urls[:2], {}, 24 * 3600, False, 10)
            self.assertEqual(candidates, ["https://rdxw.cc/", "https://rdxw.cc/sports.html"])
            self.assertIn("seen_hash", state["https://rdxw.cc/"])

    def test_submit_payload_uses_global_endpoint_shape(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch.object(indexnow_notify, "urlopen", fake_urlopen):
            status = indexnow_notify.submit_indexnow(
                "https://api.indexnow.org/indexnow",
                "rdxw.cc",
                "abc12345",
                "https://rdxw.cc/indexnow-key.txt",
                ["https://rdxw.cc/"],
                1,
            )

        self.assertEqual(status, 202)
        self.assertEqual(captured["url"], "https://api.indexnow.org/indexnow")
        self.assertEqual(captured["payload"]["host"], "rdxw.cc")
        self.assertEqual(captured["payload"]["keyLocation"], "https://rdxw.cc/indexnow-key.txt")
        self.assertEqual(captured["payload"]["urlList"], ["https://rdxw.cc/"])


if __name__ == "__main__":
    unittest.main()
