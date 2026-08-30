import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class VisionPresetTests(unittest.TestCase):
    def setUp(self):
        import config

        self.config = config
        self._originals = {
            "USER_CONFIG_DIR": config.USER_CONFIG_DIR,
            "USER_CONFIG_PATH": config.USER_CONFIG_PATH,
            "_USER_CONFIG": config._USER_CONFIG,
            "VISION_API_KEY": config.VISION_API_KEY,
            "VISION_MODEL": config.VISION_MODEL,
            "VISION_API_BASE": config.VISION_API_BASE,
        }
        self._tmp = tempfile.TemporaryDirectory()
        config.USER_CONFIG_DIR = self._tmp.name
        config.USER_CONFIG_PATH = os.path.join(self._tmp.name, "user_config.json")
        config._USER_CONFIG = {}
        config.VISION_API_KEY = ""
        config.VISION_MODEL = ""
        config.VISION_API_BASE = ""

    def tearDown(self):
        for name, value in self._originals.items():
            setattr(self.config, name, value)
        self._tmp.cleanup()

    def test_vision_preset_key_is_stored_outside_json_and_can_be_activated(self):
        stored = {}

        def get_secret(name, default=""):
            return stored.get(name, default)

        def set_secret(name, value, overwrite=False):
            stored[name] = value
            return True

        with patch("config.secret_store.get", side_effect=get_secret), \
                patch("config.secret_store.set_secret", side_effect=set_secret):
            self.assertTrue(self.config.add_vision_preset(
                "Vision Test", "vision-test-key", "test-vision-model",
                "https://vision.example/v1/chat/completions",
            ))
            raw = json.loads(Path(self.config.USER_CONFIG_PATH).read_text(encoding="utf-8"))
            self.assertNotIn("api_key", raw["vision_presets"][0])
            ref = raw["vision_presets"][0]["secret_ref"]
            self.assertTrue(ref.startswith("vision_preset_"))
            self.assertNotEqual(ref, "vision_preset_vision_test")

            self.assertTrue(self.config.set_active_vision_preset("Vision Test"))
            self.assertEqual(self.config.VISION_API_KEY, "vision-test-key")
            self.assertEqual(self.config.VISION_MODEL, "test-vision-model")
            self.assertEqual(self.config.VISION_API_BASE, "https://vision.example/v1/chat/completions")

    def test_vision_request_uses_active_provider_values(self):
        from brain import tools

        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "识图结果"}}]}
        with tempfile.NamedTemporaryFile() as image, \
                patch("brain.tools._encode_image", return_value=("encoded", "image/png")), \
                patch("brain.tools._requests.post", return_value=response) as post, \
                patch.object(tools.config, "VISION_API_KEY", "vision-test-key"), \
                patch.object(tools.config, "VISION_MODEL", "custom-vision-model"), \
                patch.object(tools.config, "VISION_API_BASE", "https://vision.example/completions"):
            self.assertEqual(tools._vision("描述图片", image.name), "识图结果")

        self.assertEqual(post.call_args.args[0], "https://vision.example/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer vision-test-key")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "custom-vision-model")

    def test_missing_vision_configuration_does_not_try_another_provider(self):
        from brain import tools

        with tempfile.NamedTemporaryFile() as image, \
                patch("brain.tools._encode_image", return_value=("encoded", "image/png")), \
                patch("brain.tools._requests.post") as post, \
                patch("brain.tools.secret_store.get", return_value=""), \
                patch.object(tools.config, "VISION_API_KEY", ""), \
                patch.object(tools.config, "VISION_MODEL", ""), \
                patch.object(tools.config, "VISION_API_BASE", ""):
            message = tools._vision("描述图片", image.name)

        self.assertIn("未启用识图模型方案", message)
        post.assert_not_called()

    def test_deleting_active_vision_preset_clears_its_runtime_configuration(self):
        stored = {}

        def get_secret(name, default=""):
            return stored.get(name, default)

        def set_secret(name, value, overwrite=False):
            stored[name] = value
            return True

        def delete_secret(name):
            stored.pop(name, None)
            return True

        with patch("config.secret_store.get", side_effect=get_secret), \
                patch("config.secret_store.set_secret", side_effect=set_secret), \
                patch("config.secret_store.delete", side_effect=delete_secret):
            self.assertTrue(self.config.add_vision_preset(
                "Delete me", "vision-test-key", "vision-model", "https://vision.example/completions"
            ))
            self.assertTrue(self.config.set_active_vision_preset("Delete me"))
            self.assertTrue(self.config.delete_vision_preset("Delete me"))

        self.assertEqual(self.config.VISION_API_KEY, "")
        self.assertEqual(self.config.get_active_vision_preset(), None)

    def test_new_chat_preset_does_not_reuse_a_legacy_name_based_key(self):
        stored = {"preset_deepseek": "stale-key"}

        def get_secret(name, default=""):
            return stored.get(name, default)

        with patch("config.secret_store.get", side_effect=get_secret):
            self.assertTrue(self.config.add_preset(
                "deepseek", "", "test-model", "https://api.example/v1"
            ))
            preset = self.config.get_presets()[0]

        self.assertNotEqual(preset["secret_ref"], "preset_deepseek")
        self.assertEqual(preset["api_key"], "")


if __name__ == "__main__":
    unittest.main()
