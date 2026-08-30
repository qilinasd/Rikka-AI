"""normalize_base_urls / fetch_model_ids：接口地址归一化与模型列表拉取。"""
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gui.model_fetcher import normalize_base_urls


class NormalizeBaseUrlsTests(unittest.TestCase):
    def test_plain_host_tries_v1_first(self):
        self.assertEqual(
            normalize_base_urls("https://api.deepseek.com"),
            ["https://api.deepseek.com/v1/models", "https://api.deepseek.com/models"],
        )

    def test_v1_base_appends_models(self):
        self.assertEqual(
            normalize_base_urls("https://api.example.com/v1/"),
            ["https://api.example.com/v1/models"],
        )

    def test_chat_completions_suffix_stripped(self):
        self.assertEqual(
            normalize_base_urls("https://x.example/v1/chat/completions"),
            ["https://x.example/v1/models"],
        )

    def test_trailing_models_passthrough(self):
        self.assertEqual(
            normalize_base_urls("https://x.example/v1/models"),
            ["https://x.example/v1/models"],
        )

    def test_invalid_inputs(self):
        self.assertEqual(normalize_base_urls(""), [])
        self.assertEqual(normalize_base_urls("ftp://x.example"), [])


if __name__ == "__main__":
    unittest.main()
