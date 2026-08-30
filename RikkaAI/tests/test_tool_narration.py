"""strip_tool_narration：剥除"口头调用工具"旁白文本（如整行"[调用 generate_image 工具]"）。"""
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain.agent import strip_tool_narration


class StripToolNarrationTests(unittest.TestCase):
    def test_trailing_bracketed_line_removed(self):
        text = "好！这次绝对不鸽你！邪王真眼之力，召唤克苏鲁之眼！\n\n[调用 generate_image 工具]"
        self.assertEqual(
            strip_tool_narration(text),
            "好！这次绝对不鸽你！邪王真眼之力，召唤克苏鲁之眼！",
        )

    def test_bare_and_fullwidth_brackets(self):
        self.assertEqual(strip_tool_narration("[调用工具]"), "")
        self.assertEqual(strip_tool_narration("【调用 generate_image 工具】"), "")
        self.assertEqual(strip_tool_narration("［调用 search_images 工具］"), "")
        self.assertEqual(strip_tool_narration("[Calling generate_image tool]"), "")

    def test_normal_text_untouched(self):
        text = "我先看看 [1] 号方案，调用接口的时候要注意参数哦"
        self.assertEqual(strip_tool_narration(text), text)

    def test_keeps_inline_mentions(self):
        text = "刚才 [调用 generate_image 工具] 这句话是我的错"
        self.assertEqual(strip_tool_narration(text), text)

    def test_empty_and_none_safe(self):
        self.assertEqual(strip_tool_narration(""), "")
        self.assertIsNone(strip_tool_narration(None))


if __name__ == "__main__":
    unittest.main()
