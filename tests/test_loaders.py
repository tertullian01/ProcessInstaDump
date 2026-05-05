import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))

from instagramdumpconverter.app import ConverterError, load_posts_from_dump


class LoaderTests(unittest.TestCase):
    def _copy_fixture(self, fixture_rel):
        src = ROOT / "tests" / "fixtures" / fixture_rel
        temp = Path(tempfile.mkdtemp(prefix="insta-fixture-"))
        dst = temp / "input"
        shutil.copytree(src, dst)
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        return dst

    def test_legacy_loader_collects_diagnostics(self):
        input_dir = self._copy_fixture("legacy")
        posts, diagnostics = load_posts_from_dump(str(input_dir))
        self.assertEqual(diagnostics["format"], "legacy-media-json")
        self.assertEqual(diagnostics["json_files_found"], 1)
        self.assertEqual(diagnostics["posts_parsed"], 2)
        self.assertGreaterEqual(diagnostics["media_files_missing"], 1)
        self.assertTrue(len(posts) >= 1)
        self.assertTrue(all("items" in p for p in posts))

    def test_modern_loader_collects_diagnostics(self):
        root_input = self._copy_fixture("modern")
        posts, diagnostics = load_posts_from_dump(str(root_input))
        self.assertEqual(diagnostics["format"], "modern-posts-json")
        self.assertEqual(diagnostics["json_files_found"], 1)
        self.assertEqual(diagnostics["posts_parsed"], 1)
        self.assertGreaterEqual(diagnostics["media_files_missing"], 1)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["caption"], "Modern caption")

    def test_missing_json_raises_typed_error(self):
        empty_root = Path(tempfile.mkdtemp(prefix="insta-empty-"))
        self.addCleanup(lambda: shutil.rmtree(empty_root, ignore_errors=True))
        with self.assertRaises(ConverterError) as ctx:
            load_posts_from_dump(str(empty_root))
        self.assertEqual(ctx.exception.code, "E_NO_INPUT_JSON")


if __name__ == "__main__":
    unittest.main()
