import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SecretStoreTests(unittest.TestCase):
    def test_preset_name_is_stable_and_non_secret(self):
        import secret_store

        self.assertEqual(secret_store.preset_name("DeepSeek"), "preset_deepseek")
        self.assertNotIn("sk-", secret_store.preset_name("DeepSeek"))

    def test_environment_has_priority(self):
        import secret_store

        with patch.dict(os.environ, {"RIKKAAI_API_KEY": "test-env-key"}, clear=False), \
                patch.object(secret_store, "_keyring", return_value=None), \
                patch.object(secret_store, "_native_get", return_value="other-key"):
            self.assertEqual(secret_store.get("global_api_key"), "test-env-key")


class MigrationTests(unittest.TestCase):
    def test_json_redaction_keeps_metadata_and_secret_ref(self):
        import migrate_secrets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory_data"
            memory.mkdir()
            (memory / "user_config.json").write_text(json.dumps({
                "api_key": "test-key",
                "presets": [{"name": "Demo", "api_key": "test-key", "model": "demo"}],
            }), encoding="utf-8")
            (memory / "partners.json").write_text(json.dumps([
                {"id": "demo", "api_key": "test-key", "name": "Demo"}
            ]), encoding="utf-8")

            migrate_secrets._strip_json_secrets(root)
            config = json.loads((memory / "user_config.json").read_text(encoding="utf-8"))
            partners = json.loads((memory / "partners.json").read_text(encoding="utf-8"))
            self.assertNotIn("api_key", config)
            self.assertNotIn("api_key", config["presets"][0])
            self.assertEqual(config["presets"][0]["secret_ref"], "preset_demo")
            self.assertNotIn("api_key", partners[0])
            self.assertEqual(partners[0]["secret_ref"], "preset_demo")


if __name__ == "__main__":
    unittest.main()
