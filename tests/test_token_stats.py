import unittest

from app.core.token_stats import (
    clamp_cache_tokens,
    request_total_tokens,
    uncached_prompt_tokens,
    summarize_token_fields,
)


class TestTokenStats(unittest.TestCase):
    def test_total_excludes_cache_subset(self):
        self.assertEqual(request_total_tokens(96947, 92, 93493), 97039)

    def test_clamp_cache_to_prompt(self):
        self.assertEqual(clamp_cache_tokens(100, 150), 100)

    def test_uncached_prompt(self):
        self.assertEqual(uncached_prompt_tokens(96947, 93493), 3454)

    def test_summarize_token_fields(self):
        summary = summarize_token_fields({
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "cache_tokens": 800,
        })
        self.assertEqual(summary["total_tokens"], 1050)
        self.assertEqual(summary["uncached_prompt_tokens"], 200)
        self.assertEqual(summary["cache_tokens"], 800)


if __name__ == "__main__":
    unittest.main()
