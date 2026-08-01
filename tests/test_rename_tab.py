import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "rename_tab.py"
SPEC = importlib.util.spec_from_file_location("rename_tab", MODULE_PATH)
rename_tab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rename_tab)


class RenameTabTests(unittest.TestCase):
    def test_extracts_tab_id_from_event(self):
        self.assertEqual(rename_tab.tab_id_from({"tab": {"tab_id": "w1:t2"}}), "w1:t2")

    def test_plain_shell_uses_directory_name(self):
        panes = [{"cwd": "/opt/plain/services"}]
        self.assertEqual(rename_tab.plain_shell_title(panes, ["zsh"]), "services")

    def test_non_shell_requires_llm(self):
        panes = [{"cwd": "/opt/plain/services"}]
        self.assertIsNone(rename_tab.plain_shell_title(panes, ["claude"]))

    def test_normalizes_model_output(self):
        self.assertEqual(rename_tab.normalize("Auth-Refactor-OAuth"), "auth-refactor-oauth")

    def test_normalizes_spaces_and_punctuation(self):
        self.assertEqual(rename_tab.normalize('"Auth refactor: OAuth!"'), "auth-refactor-oauth")

    def test_corrupt_cache_is_a_cache_miss(self):
        previous_state_dir = os.environ.get("HERDR_PLUGIN_STATE_DIR")
        with tempfile.TemporaryDirectory() as state_dir:
            os.environ["HERDR_PLUGIN_STATE_DIR"] = state_dir
            path = rename_tab.cache_path("w1:t1")
            path.parent.mkdir()
            path.write_text("not-json")
            with rename_tab.locked_tab_cache("w1:t1") as cache:
                self.assertEqual(cache, {})
        if previous_state_dir is None:
            del os.environ["HERDR_PLUGIN_STATE_DIR"]
        else:
            os.environ["HERDR_PLUGIN_STATE_DIR"] = previous_state_dir

    def test_collects_plain_text_from_panes(self):
        panes = [{"pane_id": "w1:p1", "cwd": "/repo"}]
        with patch.object(rename_tab, "herdr_text", return_value="terminal output"):
            self.assertEqual(rename_tab.pane_content(panes, 40), "[Pane: cwd=/repo]\nterminal output")

    def test_secrets_file_overrides_shared_config(self):
        previous_config_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
        with tempfile.TemporaryDirectory() as config_dir:
            os.environ["HERDR_PLUGIN_CONFIG_DIR"] = config_dir
            Path(config_dir, "config.toml").write_text('[llm]\nurl = "https://example.com"\nmodel = "test"\n')
            Path(config_dir, "secrets.toml").write_text('[llm]\napi_key = "secret"\n')
            self.assertEqual(rename_tab.load_config()["llm"]["api_key"], "secret")
        if previous_config_dir is None:
            del os.environ["HERDR_PLUGIN_CONFIG_DIR"]
        else:
            os.environ["HERDR_PLUGIN_CONFIG_DIR"] = previous_config_dir

    def test_rejects_api_key_in_shared_config(self):
        previous_config_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
        with tempfile.TemporaryDirectory() as config_dir:
            os.environ["HERDR_PLUGIN_CONFIG_DIR"] = config_dir
            Path(config_dir, "config.toml").write_text('[llm]\napi_key = "secret"\n')
            with self.assertRaisesRegex(RuntimeError, "move llm.api_key"):
                rename_tab.load_config()
        if previous_config_dir is None:
            del os.environ["HERDR_PLUGIN_CONFIG_DIR"]
        else:
            os.environ["HERDR_PLUGIN_CONFIG_DIR"] = previous_config_dir

    def test_empty_environment_key_uses_secrets_key(self):
        previous_key = os.environ.get("HERDR_AI_TAB_NAME_API_KEY")
        os.environ["HERDR_AI_TAB_NAME_API_KEY"] = ""
        self.assertEqual(rename_tab.api_key({"llm": {"api_key": "secret"}}), "secret")
        if previous_key is None:
            del os.environ["HERDR_AI_TAB_NAME_API_KEY"]
        else:
            os.environ["HERDR_AI_TAB_NAME_API_KEY"] = previous_key


if __name__ == "__main__":
    unittest.main()
