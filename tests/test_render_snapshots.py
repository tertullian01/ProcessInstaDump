import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))

from instagramdumpconverter.app import render_posts, write_output


class RenderSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path(tempfile.mkdtemp(prefix="render-snapshots-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp_root, ignore_errors=True))
        snapshot_path = ROOT / "tests" / "snapshots" / "render_signatures.json"
        self.snapshots = json.loads(snapshot_path.read_text(encoding="utf-8"))

    def _sample_posts(self):
        return [
            {
                "caption": "Snapshot caption",
                "date_label": "May 01, 2026",
                "timestamp_raw": "2026-05-01 12:00",
                "items": [{"media_type": "IMAGE", "media_url": "media/a.jpg"}],
            }
        ]

    def _signature_for(self, html_text: str):
        return "body=%s;layout=%s;memory_title=%d;caption=%d" % (
            (
                "output-theme-memory-book"
                if "output-theme-memory-book" in html_text
                else ("output-theme-minimal" if "output-theme-minimal" in html_text else "output-theme-classic")
            ),
            "posts-layout--grid" if "posts-layout--grid" in html_text else "posts-layout--stacked",
            1 if "Memory book" in html_text else 0,
            1 if "Snapshot caption" in html_text else 0,
        )

    def test_theme_layout_signatures(self):
        posts = self._sample_posts()
        for theme in ("classic", "minimal", "memory-book"):
            for layout in ("stacked", "grid"):
                out_dir = self.tmp_root / ("%s-%s" % (theme, layout))
                out_dir.mkdir(parents=True, exist_ok=True)
                html_posts = render_posts(posts, descending=True, layout=layout)
                write_output(str(out_dir), html_posts, theme=theme)
                index_html = (out_dir / "index.html").read_text(encoding="utf-8")
                key = "%s|%s" % (theme, layout)
                self.assertEqual(self.snapshots[key], self._signature_for(index_html))


if __name__ == "__main__":
    unittest.main()
