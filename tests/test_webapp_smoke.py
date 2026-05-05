import http.server
import json
import socketserver
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = ROOT / "webapp"


def make_valid_export_zip(path: Path):
    posts = [
        {
            "title": "Smoke test post",
            "creation_timestamp": 1714564800,
            "media": [{"uri": "media/posts/202605/photo1.jpg"}],
        }
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("your_instagram_activity/media/posts_1.json", json.dumps(posts))
        zf.writestr("your_instagram_activity/media/posts/202605/photo1.jpg", b"fake-image")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return


class WebappSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cwd = Path.cwd()
        cls._tmp = Path(tempfile.mkdtemp(prefix="webapp-smoke-"))
        cls.valid_zip = cls._tmp / "valid.zip"
        cls.invalid_zip = cls._tmp / "invalid.zip"
        make_valid_export_zip(cls.valid_zip)
        cls.invalid_zip.write_text("not a zip", encoding="utf-8")

        class Handler(_QuietHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(WEBAPP_DIR), **kwargs)

        cls._server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        cls.base_url = "http://127.0.0.1:%d/index.html" % cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        cls._thread.join(timeout=2)

    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:  # pragma: no cover
            self.skipTest("Playwright unavailable: %s" % exc)
        self.sync_playwright = sync_playwright

    def test_generate_preview_and_download(self):
        with self.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.base_url, wait_until="domcontentloaded")
            page.set_input_files("#fileInput", str(self.valid_zip))
            page.click("#btnGenerate")
            page.wait_for_function(
                """
                () => {
                    const status = document.querySelector("#status");
                    const btn = document.querySelector("#btnDownload");
                    if (!status || !btn) return false;
                    const ready = status.textContent && status.textContent.includes("Ready:");
                    return Boolean(ready) && btn.disabled === false;
                }
                """,
                timeout=45000,
            )
            status_text = page.locator("#status").inner_text()
            self.assertIn("Ready:", status_text)
            with page.expect_download(timeout=15000):
                page.click("#btnDownload")
            browser.close()

    def test_invalid_zip_shows_error(self):
        with self.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.base_url, wait_until="domcontentloaded")
            page.set_input_files("#fileInput", str(self.invalid_zip))
            page.click("#btnGenerate")
            page.wait_for_selector("#error:not(.d-none)", timeout=15000)
            text = page.locator("#error").inner_text().lower()
            self.assertTrue("error" in text or "invalid" in text or "zip" in text)
            browser.close()


if __name__ == "__main__":
    unittest.main()
