"""Tests for normalize_title() in src/app_runner.py."""

from pathlib import Path
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.app_runner import normalize_title, _TITLE_CACHE


class TestNormalizeTitleUnknownShow(unittest.TestCase):
    def test_passthrough_to_create_slug(self):
        result = normalize_title("Some Unknown Show", "Episode Title Here")
        self.assertEqual(result, "episode-title-here")

    def test_strips_control_characters(self):
        result = normalize_title("Unknown", "Episode\x00\x1fTitle")
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x1f", result)

    def test_unicode_title_is_slugified(self):
        result = normalize_title("Unknown", "Ünïcödé Títlé")
        self.assertTrue(result.replace("-", "").isalnum() or "-" in result)
        self.assertEqual(result, result.lower())

    def test_empty_episode_returns_empty_or_dash(self):
        result = normalize_title("Unknown", "")
        self.assertIsInstance(result, str)


class TestNormalizeTitleBehindTheBastards(unittest.TestCase):
    def test_strips_show_suffix(self):
        result = normalize_title(
            "Behind the Bastards", "Robert Evans | Behind the Bastards"
        )
        self.assertNotIn("behind the bastards", result)

    def test_no_suffix_unchanged(self):
        result = normalize_title("Behind the Bastards", "Robert Evans")
        self.assertEqual(result, "robert-evans")


class TestNormalizeTitleDarknetDiaries(unittest.TestCase):
    def test_extracts_episode_number_and_title(self):
        result = normalize_title("Darknet Diaries", "EP 123: The Big Hack")
        self.assertIn("123", result)

    def test_numeric_prefix_only(self):
        result = normalize_title("Darknet Diaries", "EP 42: Short")
        self.assertTrue(result.startswith("42"))

    def test_no_episode_prefix_falls_back_to_slug(self):
        result = normalize_title("Darknet Diaries", "Bonus Content Special")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestNormalizeTitleSwindled(unittest.TestCase):
    def test_strips_audio_podcast_suffix(self):
        result = normalize_title("Swindled", "The Big Scam | Audio Podcast")
        self.assertNotIn("audio-podcast", result)
        self.assertNotIn("audio podcast", result)

    def test_strips_documentary_suffix(self):
        result = normalize_title("Swindled", "The Big Scam | Documentary")
        self.assertNotIn("documentary", result)

    def test_no_suffix_unchanged(self):
        result = normalize_title("Swindled", "The Big Scam")
        self.assertIn("big-scam", result)


class TestNormalizeTitleCoffeeBreakSwedish(unittest.TestCase):
    def test_strips_podcast_suffix(self):
        result = normalize_title(
            "Coffee Break Swedish", "Lesson 12 | Coffee Break Swedish Podcast"
        )
        self.assertNotIn("coffee-break-swedish-podcast", result)


class TestNormalizeTitleCaching(unittest.TestCase):
    def test_second_call_returns_same_result(self):
        # Warm cache, then call again — must return same value
        r1 = normalize_title("Unknown", "Caching Test Episode")
        r2 = normalize_title("Unknown", "Caching Test Episode")
        self.assertEqual(r1, r2)

    def test_different_episodes_differ(self):
        r1 = normalize_title("Unknown", "Episode Alpha")
        r2 = normalize_title("Unknown", "Episode Beta")
        self.assertNotEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
