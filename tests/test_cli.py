import unittest
import tempfile
import os
import json
import io
from rich.console import Console
from mockdeck.cli import main

class TestCLI(unittest.TestCase):
    def test_cli_init_generates_valid_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test_db.json")
            ret = main(["init", target])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("users", data)
            self.assertIn("posts", data)
            self.assertIn("products", data)
            self.assertEqual(len(data["users"]), 3)

    def test_cli_init_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test_db.json")
            with open(target, "w", encoding="utf-8") as f:
                f.write('{"custom": []}')
            ret = main(["init", target])
            self.assertEqual(ret, 1)
            # Ensure not overwritten
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("custom", data)

    def test_cli_serve_missing_file(self):
        ret = main(["serve", "missing_file_for_sure.json"])
        self.assertEqual(ret, 1)

    def test_cli_serve_invalid_json(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as f:
            f.write("{invalid json:}")
            temp_path = f.name
        try:
            ret = main(["serve", temp_path])
            self.assertEqual(ret, 1)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_cli_no_args_shows_help(self):
        ret = main([])
        self.assertEqual(ret, 0)

if __name__ == "__main__":
    unittest.main()
