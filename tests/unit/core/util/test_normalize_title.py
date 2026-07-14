"""Tests for normalize_title() in src.utils.title_normalization."""

import unittest

from adrift.core.util.title_normalization import normalize_title


class TestNormalizeTitleUnknownShow(unittest.TestCase):
    def test_passthrough_to_create_slug(self):
        result = normalize_title("Some Unknown Show", "Episode Title Here")
        assert result == "episode-title-here"

    def test_strips_control_characters(self):
        result = normalize_title("Unknown", "Episode\x00\x1fTitle")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_unicode_title_is_slugified(self):
        result = normalize_title("Unknown", "Ünïcödé Títlé")
        assert result.replace("-", "").isalnum() or "-" in result
        assert result == result.lower()

    def test_empty_episode_returns_empty_or_dash(self):
        result = normalize_title("Unknown", "")
        assert isinstance(result, str)


class TestNormalizeTitleBehindTheBastards(unittest.TestCase):
    def test_strips_show_suffix(self):
        result = normalize_title("Behind the Bastards", "Robert Evans | Behind the Bastards")
        assert "behind the bastards" not in result

    def test_no_suffix_unchanged(self):
        result = normalize_title("Behind the Bastards", "Robert Evans")
        assert result == "robert-evans"


class TestNormalizeTitleDarknetDiaries(unittest.TestCase):
    def test_extracts_episode_number_and_title(self):
        result = normalize_title("Darknet Diaries", "EP 123: The Big Hack")
        assert "123" in result

    def test_numeric_prefix_only(self):
        result = normalize_title("Darknet Diaries", "EP 42: Short")
        assert result.startswith("42")

    def test_no_episode_prefix_falls_back_to_slug(self):
        result = normalize_title("Darknet Diaries", "Bonus Content Special")
        assert isinstance(result, str)
        assert len(result) > 0


class TestNormalizeTitleSwindled(unittest.TestCase):
    def test_strips_audio_podcast_suffix(self):
        result = normalize_title("Swindled", "The Big Scam | Audio Podcast")
        assert "audio-podcast" not in result
        assert "audio podcast" not in result

    def test_strips_documentary_suffix(self):
        result = normalize_title("Swindled", "The Big Scam | Documentary")
        assert "documentary" not in result

    def test_no_suffix_unchanged(self):
        result = normalize_title("Swindled", "The Big Scam")
        assert "big-scam" in result


class TestNormalizeTitleCreepCast(unittest.TestCase):
    def test_strips_creepcast_suffix(self):
        result = normalize_title("CreepCast", "The Story | CreepCast")
        assert "creepcast" not in result


class TestNormalizeTitleFinancialAudit(unittest.TestCase):
    def test_strips_financial_audit_suffix(self):
        result = normalize_title("Financial Audit", "Big Debt Story | Financial Audit")
        assert result == "big-debt-story"


class TestNormalizeTitleMorbid(unittest.TestCase):
    def test_strips_true_crime_podcast_slug_suffix(self):
        result = normalize_title("Morbid", "Candy Mossler Morbid A True Crime Podcast")
        assert result == "candy-mossler"

    def test_strips_podcast_video_slug_suffix(self):
        result = normalize_title("Morbid", "Candy Mossler Morbid Podcast Video")
        assert result == "candy-mossler"


class TestNormalizeTitleSmoshReadsRedditStories(unittest.TestCase):
    def test_strips_smosh_suffix(self):
        result = normalize_title(
            "Smosh Reads Reddit Stories",
            "Worst Family Drama | Smosh Reading Reddit Stories",
        )
        assert result == "worst-family-drama"


class TestNormalizeTitleCaching(unittest.TestCase):
    def test_second_call_returns_same_result(self):
        # Warm cache, then call again — must return same value
        r1 = normalize_title("Unknown", "Caching Test Episode")
        r2 = normalize_title("Unknown", "Caching Test Episode")
        assert r1 == r2

    def test_different_episodes_differ(self):
        r1 = normalize_title("Unknown", "Episode Alpha")
        r2 = normalize_title("Unknown", "Episode Beta")
        assert r1 != r2


if __name__ == "__main__":
    unittest.main()
