import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DoctorJsonTests(unittest.TestCase):
    def _copy_fixture(self, fixture_rel):
        src = ROOT / "tests" / "fixtures" / fixture_rel
        temp = Path(tempfile.mkdtemp(prefix="insta-doctor-"))
        dst = temp / "input"
        shutil.copytree(src, dst)
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        return dst

    def test_doctor_json_outputs_machine_readable_diagnostics(self):
        input_dir = self._copy_fixture("modern")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "instagramdumpconverter",
                "-i",
                str(input_dir),
                "--doctor-json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["format"], "modern-posts-json")
        self.assertEqual(payload["json_files_found"], 1)
        self.assertIn("media_files_missing", payload)

    def test_doctor_json_pretty_format_is_multiline(self):
        input_dir = self._copy_fixture("modern")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "instagramdumpconverter",
                "-i",
                str(input_dir),
                "--doctor-json-format",
                "pretty",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("\n", proc.stdout.strip())
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["format"], "modern-posts-json")

    def test_doctor_json_compact_format_has_no_spaces_between_tokens(self):
        input_dir = self._copy_fixture("modern")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "instagramdumpconverter",
                "-i",
                str(input_dir),
                "--doctor-json-format",
                "compact",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        out = proc.stdout.strip()
        self.assertTrue(out.startswith("{") and out.endswith("}"))
        self.assertNotIn("\n", out)
        self.assertIn('"format":"modern-posts-json"', out)

    def test_doctor_json_pretty_alias(self):
        input_dir = self._copy_fixture("modern")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "instagramdumpconverter",
                "-i",
                str(input_dir),
                "--doctor-json-pretty",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["format"], "modern-posts-json")
        self.assertIn("\n", proc.stdout.strip())


if __name__ == "__main__":
    unittest.main()
