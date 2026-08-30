import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.dashboard_pages import _normalize_settings_search_text


class SettingsSearchTests(unittest.TestCase):
    def test_normalizes_common_separators(self):
        self.assertEqual(
            _normalize_settings_search_text("GPT-SoVITS"),
            _normalize_settings_search_text("gptsovits"),
        )
        self.assertEqual(
            _normalize_settings_search_text("GPT SoVITS"),
            _normalize_settings_search_text("gpt_sovits"),
        )


if __name__ == "__main__":
    unittest.main()
