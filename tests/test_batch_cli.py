import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.cli import main


class BatchCliTest(unittest.TestCase):
    def invoke(self, *args):
        output = io.StringIO()
        with patch("sys.argv", ["turbo", *map(str, args)]), contextlib.redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_missing_journal_is_reported_without_creating_it(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw) / "missing"
            code, result = self.invoke("batch-status", directory)
            self.assertEqual(code, 1)
            self.assertFalse(result["valid"])
            self.assertFalse(directory.exists())

    def test_invalid_authorization_json_is_reported_without_dispatch(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            authorization = directory / "authorization.json"
            for content in ("{", "null", "[]", "{\"provider\":\"openrouter\"}"):
                with self.subTest(content=content):
                    authorization.write_text(content)
                    code, result = self.invoke("batch-dry-run", authorization, directory / "missing-pack")
                    self.assertEqual(code, 1)
                    self.assertFalse(result["valid"])
                    self.assertEqual(list(directory.iterdir()), [authorization])


if __name__ == "__main__":
    unittest.main()
