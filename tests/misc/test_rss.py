"""Tests for RSS feed parsing and generation functionality."""

from unittest.mock import Mock, patch
from datetime import datetime
from pathlib import Path
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import parse_duration
from src.web.rss import (
    upload_thumbnail,
    _extract_image_url,
    get_rss_channel,
    _extract_content_url,
    parse_rss_entry,
    get_rss_episodes,
    podcast_to_rss,
)
from src.models import RssChannel, RssEpisode


class TestUploadThumbnail(unittest.TestCase):
    """Test upload_thumbnail function."""

    @patch("src.web.rss.exists")
    @patch("src.web.rss.urljoin")
    @patch("src.web.rss.S3_ENDPOINT")
    def test_returns_existing_file_url(self, mock_endpoint, mock_urljoin, mock_exists):
        """Test that existing thumbnail URL is returned without re-uploading."""
        mock_endpoint.__str__ = lambda x: "https://s3.example.com"
        mock_exists.return_value = "existing_thumb.jpg"
        mock_urljoin.return_value = (
            "https://s3.example.com/media/podcasts/test/thumbnails/existing_thumb.jpg"
        )

        result = upload_thumbnail(
            "https://example.com/thumb.jpg", "Test Author", "test_123"
        )

        assert result is not None
        self.assertIn("existing_thumb.jpg", result)
        mock_exists.assert_called_once()

    @patch("src.web.rss.exists")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.make_square_image")
    @patch("src.web.rss.upload_file")
    def test_downloads_and_uploads_new_thumbnail(
        self, mock_upload, mock_square, mock_get, mock_exists
    ):
        """Test downloading and uploading a new thumbnail."""
        mock_exists.return_value = None
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_get.return_value = mock_response
        mock_upload.return_value = (
            "https://s3.example.com/media/podcasts/test/thumbnails/test_123.jpg"
        )

        result = upload_thumbnail(
            "https://example.com/thumb.jpg", "Test Author", "test_123"
        )

        self.assertIsNotNone(result)
        mock_get.assert_called_once()
        mock_square.assert_called_once()
        mock_upload.assert_called_once()

    @patch("src.web.rss.exists")
    @patch("src.web.rss.requests.get")
    def test_returns_none_on_failure(self, mock_get, mock_exists):
        """Test that None is returned when upload fails."""
        mock_exists.return_value = None
        mock_get.side_effect = Exception("Network error")

        result = upload_thumbnail(
            "https://example.com/thumb.jpg", "Test Author", "test_123"
        )

        self.assertIsNone(result)

    @patch("src.web.rss.exists")
    @patch("src.web.rss.requests.get")
    def test_unknown_mime_type_returns_none(self, mock_get, mock_exists):
        """B4 fix: unrecognised Content-Type must return None, not raise AssertionError."""
        mock_exists.return_value = None
        mock_response = Mock()
        mock_response.content = b"binary blob"
        mock_response.headers = {"Content-Type": "application/octet-stream"}
        mock_get.return_value = mock_response

        result = upload_thumbnail(
            "https://example.com/thumb.bin", "Test Author", "test_456"
        )

        self.assertIsNone(result)


class TestExtractImageUrl(unittest.TestCase):
    """Test _extract_image_url helper function."""

    def test_extracts_from_image_href(self):
        """Test extracting image from channel.image.href."""
        channel = Mock(spec=["image", "get"])
        image_mock = Mock()
        image_mock.href = "https://example.com/image.jpg"
        image_mock.get = lambda key, default=None: (
            "https://example.com/image.jpg" if key == "href" else default
        )
        channel.image = image_mock
        channel.get = lambda key, default=None: (
            channel.image if key == "image" else default
        )

        result = _extract_image_url(channel)

        self.assertEqual(result, "https://example.com/image.jpg")

    def test_extracts_from_image_url(self):
        """Test extracting image from channel.image.url."""
        channel = Mock(spec=["image", "get"])
        image_mock = Mock(spec=["url", "get"])  # Only url, not href
        image_mock.url = "https://example.com/image.jpg"
        image_mock.get = lambda key, default=None: (
            "https://example.com/image.jpg" if key == "url" else default
        )
        channel.image = image_mock
        channel.get = lambda key, default=None: (
            channel.image if key == "image" else default
        )

        result = _extract_image_url(channel)

        self.assertEqual(result, "https://example.com/image.jpg")

    def test_extracts_from_itunes_image(self):
        """Test extracting image from itunes_image."""
        channel = Mock()
        channel.itunes_image = "https://example.com/itunes.jpg"
        channel.get = lambda key, default=None: (
            channel.itunes_image if key == "itunes_image" else None
        )
        delattr(channel, "image")

        result = _extract_image_url(channel)

        self.assertEqual(result, "https://example.com/itunes.jpg")

    def test_returns_empty_when_no_image(self):
        """Test returns empty string when no image found."""
        channel = Mock()
        delattr(channel, "image")
        delattr(channel, "itunes_image")
        channel.get = lambda key, default=None: default

        result = _extract_image_url(channel)

        self.assertEqual(result, "")


class TestGetRssChannel(unittest.TestCase):
    """Test get_rss_channel function."""

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_parses_rss_channel(self, mock_parse, mock_get, mock_cache_fn):
        """Test parsing RSS feed to extract channel information."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None

        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        mock_feed = Mock()
        mock_feed.bozo = False
        mock_channel = Mock()
        mock_channel.title = "Test Podcast"
        mock_channel.author = "Test Author"
        mock_channel.subtitle = "Test Subtitle"
        mock_channel.url = "https://example.com"
        mock_channel.description = "Test Description"

        # Setup image mock with proper get() method
        image_mock = Mock()
        image_mock.href = "https://example.com/image.jpg"
        image_mock.get = lambda key, default=None: (
            "https://example.com/image.jpg" if key == "href" else default
        )
        mock_channel.image = image_mock

        mock_channel.get = lambda key, default=None: getattr(mock_channel, key, default)
        delattr(mock_channel, "itunes_image")  # Ensure no itunes_image attribute
        mock_feed.feed = mock_channel
        mock_parse.return_value = mock_feed

        result = get_rss_channel("https://example.com/feed.xml")

        self.assertIsInstance(result, RssChannel)
        self.assertEqual(result.title, "Test Podcast")
        self.assertEqual(result.author, "Test Author")
        self.assertEqual(result.description, "Test Description")

    @patch("src.web.rss._rss_cache")
    def test_uses_cached_feed(self, mock_cache_fn):
        """Test that cached feed is used when available."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = "<rss>cached feed</rss>"

        with patch("src.web.rss.feedparser.parse") as mock_parse:
            mock_feed = Mock()
            mock_feed.bozo = False
            mock_channel = Mock(spec=[])  # Empty spec to prevent auto-mocking
            mock_channel.title = "Cached Podcast"
            mock_channel.author = ""
            mock_channel.itunes_author = ""
            mock_channel.creator = ""
            mock_channel.subtitle = ""
            mock_channel.itunes_subtitle = ""
            mock_channel.url = ""
            mock_channel.description = ""
            mock_channel.summary = ""

            mock_channel.get = lambda key, default=None: getattr(
                mock_channel, key, default
            )
            mock_feed.feed = mock_channel
            mock_parse.return_value = mock_feed

            result = get_rss_channel("https://example.com/feed.xml")

            self.assertEqual(result.title, "Cached Podcast")
            self.assertEqual(result.author, "")
            self.assertEqual(result.description, "")
            mock_cache.get.assert_called_once()


class TestParseDuration(unittest.TestCase):
    """Test parse_duration helper function."""

    def test_parses_hhmmss_format(self):
        """Test parsing HH:MM:SS format."""
        result = parse_duration("01:30:45")

        self.assertEqual(result, 5445.0)  # 1*3600 + 30*60 + 45

    def test_parses_mmss_format(self):
        """Test parsing MM:SS format."""
        result = parse_duration("15:30")

        self.assertEqual(result, 930.0)  # 15*60 + 30

    def test_parses_seconds_only(self):
        """Test parsing seconds only."""
        result = parse_duration("123.5")

        self.assertEqual(result, 123.5)

    def test_returns_none_for_invalid(self):
        """Test returns None for None input."""
        result = parse_duration("")

        self.assertIsNone(result, f"Expected None, got {result}")

    def test_parses_large_seconds_only(self):
        """Test parsing large seconds-only format (real-world: Swindled podcast)."""
        result = parse_duration("4765")

        self.assertEqual(result, 4765.0)

    def test_parses_long_hhmmss_format(self):
        """Test parsing long HH:MM:SS over 1 hour (real-world: Pod Save America)."""
        result = parse_duration("01:37:34")

        # 1*3600 + 37*60 + 34 = 3600 + 2220 + 34 = 5854
        self.assertEqual(result, 5854.0)

    def test_parses_short_hhmmss_less_than_minute(self):
        """Test parsing very short HH:MM:SS (real-world: Dateline NBC trailer)."""
        result = parse_duration("00:00:58")

        self.assertEqual(result, 58.0)

    def test_parses_hhmmss_with_float_seconds(self):
        """B2 fix: iTunes feeds often send fractional seconds like 1:02:30.5."""
        result = parse_duration("1:02:30.5")
        self.assertAlmostEqual(result, 3750.5)

    def test_parses_mmss_with_float_seconds(self):
        """B2 fix: MM:SS.f variant."""
        result = parse_duration("02:30.5")
        self.assertAlmostEqual(result, 150.5)


class TestExtractContentUrl(unittest.TestCase):
    """Test _extract_content_url helper function."""

    def test_extracts_from_enclosures(self):
        """Test extracting URL from enclosures."""
        entry = Mock()
        entry.enclosures = [{"href": "https://example.com/episode.mp3"}]

        result = _extract_content_url(entry)

        self.assertEqual(result, "https://example.com/episode.mp3")

    def test_filters_non_audio_urls(self):
        """Test that non-audio URLs are filtered out."""
        entry = Mock()
        entry.enclosures = [
            {"href": "https://example.com/image.jpg"},
            {"href": "https://example.com/episode.mp3"},
        ]

        result = _extract_content_url(entry)

        self.assertEqual(result, "https://example.com/episode.mp3")

    def test_extracts_from_url_attribute(self):
        """Test extracting from url attribute when no enclosures."""
        entry = Mock()
        entry.enclosures = []
        entry.url = "https://example.com/episode.m4a"
        entry.get = lambda key, default="": entry.url if key == "url" else default

        result = _extract_content_url(entry)

        self.assertEqual(result, "https://example.com/episode.m4a")

    def test_returns_none_when_no_audio_found(self):
        """Test returns None when no audio URL found."""
        entry = Mock()
        entry.enclosures = [{"href": "https://example.com/image.jpg"}]

        result = _extract_content_url(entry)

        self.assertIsNone(result)


class TestParseRssEntry(unittest.TestCase):
    """Test parse_rss_entry function."""

    def test_parses_complete_entry(self):
        """Test parsing entry with all fields."""
        entry = Mock()
        entry.id = "episode_123"
        entry.title = "Test Episode"
        entry.author = "Test Author"
        entry.description = "Test Description"
        entry.published = "2023-12-18T10:30:00"
        entry.itunes_duration = "1800"  # 30 minutes
        entry.enclosures = [{"href": "https://example.com/episode.mp3"}]
        entry.itunes_image = "https://example.com/thumb.jpg"

        result = parse_rss_entry(entry)

        self.assertIsInstance(result, RssEpisode)
        self.assertEqual(result.id, "episode_123")
        self.assertEqual(result.title, "Test Episode")
        self.assertEqual(result.author, "Test Author")
        self.assertEqual(result.content, "https://example.com/episode.mp3")
        self.assertEqual(result.duration, 1800.0)
        self.assertIsInstance(result.pub_date, datetime)

    def test_handles_missing_optional_fields(self):
        """Test parsing entry with minimal fields."""
        entry = Mock()
        entry.id = "episode_456"
        entry.title = "Minimal Episode"
        for attr in ["author", "description", "itunes_duration"]:
            setattr(entry, attr, "")
        entry.published = "2023-12-18T10:30:00"
        entry.enclosures = [{"href": "https://example.com/episode.mp3"}]
        delattr(entry, "itunes_image")
        delattr(entry, "image")

        result = parse_rss_entry(entry)

        self.assertEqual(result.id, "episode_456")
        self.assertEqual(result.title, "Minimal Episode")
        self.assertIsNone(result.duration)

    def test_naive_pub_date_gets_utc_timezone(self):
        """B3 fix: feeds with no timezone should produce a tz-aware datetime."""
        from datetime import timezone

        entry = Mock()
        entry.id = "ep_tz"
        entry.title = "TZ Test"
        entry.author = ""
        entry.description = ""
        entry.published = "Mon, 18 Dec 2023 10:30:00"  # No TZ
        entry.enclosures = [{"href": "https://example.com/ep.mp3"}]
        delattr(entry, "itunes_duration")
        delattr(entry, "itunes_image")
        delattr(entry, "image")

        result = parse_rss_entry(entry)

        self.assertIsNotNone(result.pub_date.tzinfo)
        self.assertEqual(result.pub_date.tzinfo, timezone.utc)

    def test_explicit_timezone_is_preserved(self):
        """B3 fix: entries with an explicit offset should keep it."""
        entry = Mock()
        entry.id = "ep_tz2"
        entry.title = "TZ Test 2"
        entry.author = ""
        entry.description = ""
        entry.published = "Mon, 18 Dec 2023 10:30:00 +0500"
        entry.enclosures = [{"href": "https://example.com/ep.mp3"}]
        delattr(entry, "itunes_duration")
        delattr(entry, "itunes_image")
        delattr(entry, "image")

        result = parse_rss_entry(entry)

        self.assertIsNotNone(result.pub_date.tzinfo)
        # Offset should be +5 hours, not zeroed to UTC
        import datetime
        self.assertEqual(result.pub_date.utcoffset(), datetime.timedelta(hours=5))


class TestGetRssEpisodes(unittest.TestCase):
    """Test get_rss_episodes function."""

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_fetches_and_parses_episodes(self, mock_parse, mock_get, mock_cache_fn):
        """Test fetching and parsing RSS episodes."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None

        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = Mock()
        entry1.id = "ep1"
        entry1.title = "Episode 1"
        for attr in ["author", "description"]:
            setattr(entry1, attr, "")
        entry1.published = "2023-12-18T10:00:00"
        entry1.enclosures = [{"href": "https://example.com/ep1.mp3"}]
        for attr in ["itunes_duration", "itunes_image", "image"]:
            delattr(entry1, attr)

        entry2 = Mock()
        entry2.id = "ep2"
        entry2.title = "Episode 2"
        for attr in ["author", "description"]:
            setattr(entry2, attr, "")
        entry2.published = "2023-12-17T10:00:00"
        entry2.enclosures = [{"href": "https://example.com/ep2.mp3"}]
        for attr in ["itunes_duration", "itunes_image", "image"]:
            delattr(entry2, attr)

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes("https://example.com/feed.xml")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "ep1")
        self.assertEqual(result[1].id, "ep2")

    @patch("src.web.rss._rss_cache")
    @patch("src.web.rss.requests.get")
    @patch("src.web.rss.feedparser.parse")
    def test_filters_episodes_by_regex(self, mock_parse, mock_get, mock_cache_fn):
        """Test filtering episodes using regex."""
        mock_cache = mock_cache_fn.return_value
        mock_cache.get.return_value = None

        mock_response = Mock()
        mock_response.text = "<rss>fake feed</rss>"
        mock_get.return_value = mock_response

        entry1 = Mock()
        entry1.id = "ep1"
        entry1.title = "Special Episode 1"
        for attr in ["author", "description"]:
            setattr(entry1, attr, "")
        entry1.published = "2023-12-18T10:00:00"
        entry1.enclosures = [{"href": "https://example.com/ep1.mp3"}]
        for attr in ["itunes_duration", "itunes_image", "image"]:
            delattr(entry1, attr)

        entry2 = Mock()
        entry2.id = "ep2"
        entry2.title = "Regular Episode 2"
        for attr in ["author", "description"]:
            setattr(entry2, attr, "")
        entry2.published = "2023-12-17T10:00:00"
        entry2.enclosures = [{"href": "https://example.com/ep2.mp3"}]
        for attr in ["itunes_duration", "itunes_image", "image"]:
            delattr(entry2, attr)

        mock_feed = Mock()
        mock_feed.entries = [entry1, entry2]
        mock_parse.return_value = mock_feed

        result = get_rss_episodes("https://example.com/feed.xml", filter="Special")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Special Episode 1")


class TestPodcastToRss(unittest.TestCase):
    """Test podcast_to_rss function."""

    def test_generates_valid_rss_xml(self):
        """Test generating RSS XML from channel and episodes."""
        channel = RssChannel(
            title="Test Podcast",
            author="Test Author",
            subtitle="Test Subtitle",
            url="https://example.com",
            description="Test Description",
            image="https://example.com/image.jpg",
        )

        episodes = [
            RssEpisode(
                id="ep1",
                title="Episode 1",
                author="Test Author",
                description="Episode 1 description",
                content="https://example.com/ep1.mp3",
                pub_date=datetime(2023, 12, 18, 10, 30),
                duration=1800.0,
                image="https://example.com/ep1.jpg",
            ),
        ]

        result = podcast_to_rss(channel, episodes)

        # Verify it's valid XML
        self.assertIn("<?xml version", result)
        self.assertIn('version="2.0"', result)
        self.assertIn("<channel>", result)
        self.assertIn("<title>Test Podcast</title>", result)
        self.assertIn("<item>", result)
        self.assertIn("<guid>ep1</guid>", result)

    def test_handles_empty_episodes(self):
        """Test generating RSS with no episodes."""
        channel = RssChannel(
            title="Empty Podcast",
            author="Test Author",
            subtitle="",
            url="https://example.com",
            description="No episodes yet",
            image="",
        )

        result = podcast_to_rss(channel, [])

        self.assertIn("<channel>", result)
        self.assertIn("<title>Empty Podcast</title>", result)
        self.assertNotIn("<item>", result)

    def test_handles_missing_optional_fields(self):
        """Test generating RSS with minimal fields."""
        channel = RssChannel(
            title="Minimal Podcast",
            author="",
            subtitle="",
            url="",
            description="",
            image="",
        )

        episodes = [
            RssEpisode(
                id="ep1",
                title="Episode 1",
                author="",
                description=None,
                content="https://example.com/ep1.mp3",
                pub_date=None,
                duration=None,
                image=None,
            ),
        ]

        result = podcast_to_rss(channel, episodes)

        self.assertIn("<channel>", result)
        self.assertIn("<title>Minimal Podcast</title>", result)
        self.assertIn("<guid>ep1</guid>", result)


if __name__ == "__main__":
    unittest.main()
