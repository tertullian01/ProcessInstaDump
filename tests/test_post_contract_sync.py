import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PostContractSyncTests(unittest.TestCase):
    def test_shared_and_web_contract_files_match(self):
        shared = json.loads((ROOT / "shared" / "post_contract.json").read_text(encoding="utf-8"))
        web = json.loads((ROOT / "webapp" / "assets" / "post_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(shared, web)


if __name__ == "__main__":
    unittest.main()
