"""Tests for RSS feed filtering functionality (feed_filter and feed_day_of_week_filter)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.web.rss import get_rss_episodes


def _create_mock_entry(id: str, title: str, pub_date: str) -> Mock:
    """Create a mock RSS entry for testing."""
    entry = Mock()
    entry.id = id
    entry.title = title
    entry.author = ""
    entry.description = ""
    entry.published = pub_date
    entry.pubDate = pub_date
    entry.enclosures = [{"href": f"https://example.com/{id}.mp3"}]
    for attr in ["itunes_duration", "itunes_image", "image"]:
        if hasattr(entry, attr):
            delattr(entry, attr)
    return entry


class TestFeedFilter(unittest.TestCase):
    """Test feed_filter (regex) functionality."""

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filter_includes_matching_episodes(
        self, mock_parse, mock_get, mock_cache_fn
    ):
        """Test that episodes matching the filter regex are included."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        # Create test entries
        entry1 = _create_mock_entry(
            "ep1", "Episode 001: Introduction", "2023-12-18T10:00:00"
        )
        entry2 = _create_mock_entry(
            "ep2", "Episode 002: Deep Dive", "2023-12-17T10:00:00"
        )
        entry3 = _create_mock_entry(
            "ep3", "Bonus: Behind the Scenes", "2023-12-16T10:00:00"
        )

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2, entry3]
        mock_parse.return_value = mock_feed

        # Filter for "Episode" in title
        result = get_rss_episodes("https://example.com/feed.xml", filter="Episode")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Episode 001: Introduction")
        self.assertEqual(result[1].title, "Episode 002: Deep Dive")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filter_excludes_non_matching_episodes(
        self, mock_parse, mock_get, mock_cache_fn
    ):
        """Test that episodes not matching the filter regex are excluded."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = _create_mock_entry("ep1", "Regular Episode", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "Overtime Show", "2023-12-17T10:00:00")
        entry3 = _create_mock_entry("ep3", "Trivia Night", "2023-12-16T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2, entry3]
        mock_parse.return_value = mock_feed

        # Filter to exclude "Overtime" and "Trivia"
        result = get_rss_episodes(
            "https://example.com/feed.xml", filter="^(?!.*Overtime)(?!.*Trivia).*$"
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Regular Episode")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filter_case_insensitive(self, mock_parse, mock_get, mock_cache_fn):
        """Test that filter can be case-insensitive with (?i) flag."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = _create_mock_entry("ep1", "SPECIAL EPISODE", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "special bonus", "2023-12-17T10:00:00")
        entry3 = _create_mock_entry("ep3", "Regular Show", "2023-12-16T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2, entry3]
        mock_parse.return_value = mock_feed

        # Case-insensitive filter for "special"
        result = get_rss_episodes("https://example.com/feed.xml", filter="(?i)special")

        self.assertEqual(len(result), 2)
        self.assertIn("SPECIAL", result[0].title)
        self.assertIn("special", result[1].title)

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filter_empty_string_returns_all(self, mock_parse, mock_get, mock_cache_fn):
        """Test that empty filter string returns all episodes."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = _create_mock_entry("ep1", "Episode 1", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "Episode 2", "2023-12-17T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes("https://example.com/feed.xml", filter="")

        self.assertEqual(len(result), 2)

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filter_none_returns_all(self, mock_parse, mock_get, mock_cache_fn):
        """Test that None filter returns all episodes."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = _create_mock_entry("ep1", "Episode 1", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "Episode 2", "2023-12-17T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes("https://example.com/feed.xml", filter=None)

        self.assertEqual(len(result), 2)


class TestDayOfWeekFilter(unittest.TestCase):
    """Test r_rules (RFC 5545) episode date filtering."""

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filters_weekdays_only(self, mock_parse, mock_get, mock_cache_fn):
        """Test filtering for weekdays only (Mon-Fri)."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        # Dec 18, 2023 = Monday, Dec 17 = Sunday, Dec 16 = Saturday, Dec 15 = Friday
        entry_mon = _create_mock_entry("ep1", "Monday Episode", "2023-12-18T10:00:00")
        entry_sun = _create_mock_entry("ep2", "Sunday Episode", "2023-12-17T10:00:00")
        entry_sat = _create_mock_entry("ep3", "Saturday Episode", "2023-12-16T10:00:00")
        entry_fri = _create_mock_entry("ep4", "Friday Episode", "2023-12-15T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry_mon, entry_sun, entry_sat, entry_fri]
        mock_parse.return_value = mock_feed

        # Filter for weekdays only
        result = get_rss_episodes(
            "https://example.com/feed.xml",
            r_rules=[
                "FREQ=WEEKLY;BYDAY=MO",
                "FREQ=WEEKLY;BYDAY=TU",
                "FREQ=WEEKLY;BYDAY=WE",
                "FREQ=WEEKLY;BYDAY=TH",
                "FREQ=WEEKLY;BYDAY=FR",
            ],
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Monday Episode")
        self.assertEqual(result[1].title, "Friday Episode")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filters_weekend_only(self, mock_parse, mock_get, mock_cache_fn):
        """Test filtering for weekend only (Sat-Sun)."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry_mon = _create_mock_entry("ep1", "Monday Episode", "2023-12-18T10:00:00")
        entry_sun = _create_mock_entry("ep2", "Sunday Episode", "2023-12-17T10:00:00")
        entry_sat = _create_mock_entry("ep3", "Saturday Episode", "2023-12-16T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry_mon, entry_sun, entry_sat]
        mock_parse.return_value = mock_feed

        # Filter for weekend only
        result = get_rss_episodes(
            "https://example.com/feed.xml",
            r_rules=["FREQ=WEEKLY;BYDAY=SA", "FREQ=WEEKLY;BYDAY=SU"],
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Sunday Episode")
        self.assertEqual(result[1].title, "Saturday Episode")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filters_single_day(self, mock_parse, mock_get, mock_cache_fn):
        """Test filtering for a single specific day."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        # Dec 18 = Monday, Dec 19 = Tuesday, Dec 20 = Wednesday
        entry_mon = _create_mock_entry("ep1", "Monday Episode", "2023-12-18T10:00:00")
        entry_tue = _create_mock_entry("ep2", "Tuesday Episode", "2023-12-19T10:00:00")
        entry_wed = _create_mock_entry(
            "ep3", "Wednesday Episode", "2023-12-20T10:00:00"
        )

        mock_feed = Mock()
        mock_feed.entries = [entry_mon, entry_tue, entry_wed]
        mock_parse.return_value = mock_feed

        # Filter for Wednesday only
        result = get_rss_episodes(
            "https://example.com/feed.xml", r_rules=["FREQ=WEEKLY;BYDAY=WE"]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Wednesday Episode")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_empty_day_filter_returns_all(self, mock_parse, mock_get, mock_cache_fn):
        """Test that empty feed_day_of_week_filter returns all episodes."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = _create_mock_entry("ep1", "Episode 1", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "Episode 2", "2023-12-17T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes("https://example.com/feed.xml", r_rules=[])

        self.assertEqual(len(result), 2)

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_none_day_filter_returns_all(self, mock_parse, mock_get, mock_cache_fn):
        """Test that None r_rules returns all episodes."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = _create_mock_entry("ep1", "Episode 1", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "Episode 2", "2023-12-17T10:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes("https://example.com/feed.xml", r_rules=None)

        self.assertEqual(len(result), 2)

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_handles_missing_pub_date(self, mock_parse, mock_get, mock_cache_fn):
        """Test that episodes with missing pub_date are excluded when using day filter."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry_valid = _create_mock_entry("ep1", "Valid Episode", "2023-12-18T10:00:00")
        entry_missing = _create_mock_entry("ep2", "Missing Date", "")

        mock_feed = Mock()
        mock_feed.entries = [entry_valid, entry_missing]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes(
            "https://example.com/feed.xml", r_rules=["FREQ=WEEKLY;BYDAY=MO"]
        )

        # Only the valid entry should be returned (missing date is excluded)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Valid Episode")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_handles_invalid_pub_date(self, mock_parse, mock_get, mock_cache_fn):
        """Test that episodes with invalid pub_date format are excluded when using r_rules."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry_valid = _create_mock_entry("ep1", "Valid Episode", "2023-12-18T10:00:00")
        entry_invalid = _create_mock_entry("ep2", "Invalid Date", "not-a-date")

        mock_feed = Mock()
        mock_feed.entries = [entry_valid, entry_invalid]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes(
            "https://example.com/feed.xml", r_rules=["FREQ=WEEKLY;BYDAY=MO"]
        )

        # Only the valid entry should be returned (invalid date is excluded)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Valid Episode")


class TestCombinedFilters(unittest.TestCase):
    """Test combining feed_filter and r_rules."""

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_both_filters_applied(self, mock_parse, mock_get, mock_cache_fn):
        """Test that both feed_filter and r_rules are applied together."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        # Create entries with different titles and dates
        # Dec 18 = Monday, Dec 17 = Sunday, Dec 19 = Tuesday
        entry1 = _create_mock_entry(
            "ep1", "Episode 001", "2023-12-18T10:00:00"
        )  # Mon, matches both
        entry2 = _create_mock_entry(
            "ep2", "Episode 002", "2023-12-17T10:00:00"
        )  # Sun, title matches, day doesn't
        entry3 = _create_mock_entry(
            "ep3", "Bonus Show", "2023-12-18T10:00:00"
        )  # Mon, day matches, title doesn't
        entry4 = _create_mock_entry(
            "ep4", "Episode 003", "2023-12-19T10:00:00"
        )  # Tue, matches both

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2, entry3, entry4]
        mock_parse.return_value = mock_feed

        # Apply both filters
        result = get_rss_episodes(
            "https://example.com/feed.xml",
            filter="Episode",
            r_rules=["FREQ=WEEKLY;BYDAY=MO", "FREQ=WEEKLY;BYDAY=TU"],
        )

        # Only episodes that match BOTH filters should be returned
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Episode 001")
        self.assertEqual(result[1].title, "Episode 003")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_complex_regex_with_day_filter(self, mock_parse, mock_get, mock_cache_fn):
        """Test complex regex exclusion filter combined with day filter."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        # Dec 18 = Monday, Dec 19 = Tuesday
        entry1 = _create_mock_entry("ep1", "Main Show", "2023-12-18T10:00:00")
        entry2 = _create_mock_entry("ep2", "Overtime Special", "2023-12-18T11:00:00")
        entry3 = _create_mock_entry("ep3", "Main Show", "2023-12-19T10:00:00")
        entry4 = _create_mock_entry("ep4", "Trivia Night", "2023-12-19T11:00:00")

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2, entry3, entry4]
        mock_parse.return_value = mock_feed

        # Exclude "Overtime" and "Trivia", only weekdays
        result = get_rss_episodes(
            "https://example.com/feed.xml",
            filter="^(?!.*Overtime)(?!.*Trivia).*$",
            r_rules=[
                "FREQ=WEEKLY;BYDAY=MO",
                "FREQ=WEEKLY;BYDAY=TU",
                "FREQ=WEEKLY;BYDAY=WE",
                "FREQ=WEEKLY;BYDAY=TH",
                "FREQ=WEEKLY;BYDAY=FR",
            ],
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Main Show")
        self.assertEqual(result[1].title, "Main Show")

    # Helper method
    def _create_mock_entry(self, id: str, title: str, pub_date: str) -> Mock:
        """Create a mock RSS entry for testing."""
        entry = Mock()
        entry.id = id
        entry.title = title
        entry.author = ""
        entry.description = ""
        entry.published = pub_date
        entry.pubDate = pub_date
        entry.enclosures = [{"href": f"https://example.com/{id}.mp3"}]
        for attr in ["itunes_duration", "itunes_image", "image"]:
            if hasattr(entry, attr):
                delattr(entry, attr)
        return entry


class TestCacheKeyGeneration(unittest.TestCase):
    """Test that cache keys are generated correctly with filter parameters."""

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_cache_key_includes_day_filter(self, mock_parse, mock_get, mock_cache_fn):
        """Test that cache key includes r_rules to prevent wrong cached results."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = TestCombinedFilters()._create_mock_entry(
            "ep1", "Episode", "2023-12-18T10:00:00"
        )

        mock_feed = Mock()
        mock_feed.entries = [entry1]
        mock_parse.return_value = mock_feed

        # First call with weekday r_rules
        get_rss_episodes(
            "https://example.com/feed.xml",
            r_rules=[
                "FREQ=WEEKLY;BYDAY=MO",
                "FREQ=WEEKLY;BYDAY=TU",
                "FREQ=WEEKLY;BYDAY=WE",
                "FREQ=WEEKLY;BYDAY=TH",
                "FREQ=WEEKLY;BYDAY=FR",
            ],
        )

        # Verify cache.get was called with a key that includes the r_rules
        call_args = mock_cache.get.call_args[0][0]
        self.assertIn("FREQ=WEEKLY;BYDAY=FR", call_args)

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_cache_key_converts_list_to_tuple(
        self, mock_parse, mock_get, mock_cache_fn
    ):
        """Test that r_rules list is serialized into a hashable cache key."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None
        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = TestCombinedFilters()._create_mock_entry(
            "ep1", "Episode", "2023-12-18T10:00:00"
        )

        mock_feed = Mock()
        mock_feed.entries = [entry1]
        mock_parse.return_value = mock_feed

        # This should not raise an error about unhashable type
        result = get_rss_episodes(
            "https://example.com/feed.xml",
            r_rules=["FREQ=WEEKLY;BYDAY=MO", "FREQ=WEEKLY;BYDAY=TU"],
        )

        # Should complete without error
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
