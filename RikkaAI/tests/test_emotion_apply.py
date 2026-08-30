"""apply_emotion_values：情感面板「设置」的手动数值写回。"""
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain.agent import AgentCore


class ApplyEmotionValuesTests(unittest.TestCase):
    def test_basic_fields_applied(self):
        core = AgentCore()
        core.apply_emotion_values({"mood": "happy", "emotion_energy": 88, "affection": 95})
        self.assertEqual(core.emotion.mood, "happy")
        self.assertEqual(core.emotion.energy, 88)
        self.assertEqual(core.emotion.affection, 95)

    def test_invalid_mood_ignored(self):
        core = AgentCore()
        core.apply_emotion_values({"mood": "ecstatic"})
        self.assertEqual(core.emotion.mood, "neutral")

    def test_values_clamped(self):
        core = AgentCore()
        core.apply_emotion_values({"emotion_energy": 250, "affection": -5})
        self.assertEqual(core.emotion.energy, 100)
        self.assertEqual(core.emotion.affection, 0)

    def test_needs_applied_when_enabled(self):
        core = AgentCore()
        core.get_emotion_snapshot()  # 懒建 _needs（emotion_needs_enabled 默认开启）
        core.apply_emotion_values({"social": 90, "loneliness": 5})
        self.assertEqual(core._needs.social, 90)
        self.assertEqual(core._needs.loneliness, 5)

    def test_needs_skipped_when_absent(self):
        core = AgentCore()
        core._needs = None
        core.apply_emotion_values({"social": 90})  # 不应抛异常


if __name__ == "__main__":
    unittest.main()
