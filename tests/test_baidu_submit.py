import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "baidu_submit.py"
SPEC = importlib.util.spec_from_file_location("baidu_submit", MODULE_PATH)
baidu_submit = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(baidu_submit)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"success":1,"remain":499999}'


class BaiduSubmitTests(unittest.TestCase):
    def test_sitemap_index_and_due_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            urls = baidu_submit.sitemap_urls(root, root / "sitemap.xml")
            self.assertEqual(urls, ["https://rdxw.cc/", "https://rdxw.cc/sports.html", "https://other.example/page.html"])
            own_urls = [url for url in urls if url.startswith("https://rdxw.cc/")]
            candidates, state = baidu_submit.due_urls(root, "https://rdxw.cc", own_urls, {}, 7 * 24 * 3600, False, 10)
            self.assertEqual(candidates, ["https://rdxw.cc/", "https://rdxw.cc/sports.html"])
            self.assertIn("seen_hash", state["https://rdxw.cc/"])

    def test_submit_payload_uses_baidu_endpoint_shape(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = request.data.decode("utf-8")
            captured["content_type"] = request.headers["Content-type"]
            return FakeResponse()

        with patch.object(baidu_submit, "urlopen", fake_urlopen):
            result = baidu_submit.submit_baidu(
                "http://data.zz.baidu.com/urls",
                "rdxw.cc",
                "test-token",
                ["https://rdxw.cc/", "https://rdxw.cc/sports.html"],
                1,
            )

        self.assertEqual(result["http_status"], 200)
        self.assertEqual(captured["url"], "http://data.zz.baidu.com/urls?site=rdxw.cc&token=test-token")
        self.assertEqual(captured["body"], "https://rdxw.cc/\nhttps://rdxw.cc/sports.html")
        self.assertEqual(captured["content_type"], "text/plain")


if __name__ == "__main__":
    unittest.main()
