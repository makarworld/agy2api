import os
import unittest

from app.core import auto_classifier


CLASSIFIER_PROMPT = """<transcript>
 User: https://t.me/addemoji/CPT_Emoji Вот ссылка
 Bash dir
 </transcript>

Err on the side of blocking. Stage 1 does NOT apply user intent or ALLOW exceptions — stage 2 will handle those.
Your ENTIRE response MUST begin with <block>. Do NOT output any analysis, reasoning, or commentary before <block>."""


class TestAutoClassifier(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ.pop("AGY_AUTO_CLASSIFIER_SHORTCUT", None)
        os.environ.pop("AGY_AUTO_CLASSIFIER_RESPONSE", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_detects_classifier_prompt(self):
        messages = [{"role": "user", "content": CLASSIFIER_PROMPT}]
        self.assertTrue(auto_classifier.is_auto_classifier_request(messages))

    def test_ignores_normal_chat(self):
        messages = [{"role": "user", "content": "Hello, help me write Python"}]
        self.assertFalse(auto_classifier.is_auto_classifier_request(messages))

    def test_ignores_transcript_without_block_rules(self):
        messages = [{"role": "user", "content": "<transcript>\nUser: hi\n</transcript>"}]
        self.assertFalse(auto_classifier.is_auto_classifier_request(messages))

    def test_shortcut_disabled_by_default(self):
        self.assertFalse(auto_classifier.shortcut_enabled())

    def test_shortcut_enabled_via_env(self):
        os.environ["AGY_AUTO_CLASSIFIER_SHORTCUT"] = "true"
        self.assertTrue(auto_classifier.shortcut_enabled())

    def test_custom_response(self):
        os.environ["AGY_AUTO_CLASSIFIER_RESPONSE"] = "<block>yes</block>"
        self.assertEqual(auto_classifier.shortcut_response(), "<block>yes</block>")


if __name__ == "__main__":
    unittest.main()
