import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from src.models.metadata import RssEpisode


class TestRssEpisodeFromYtdlp(unittest.TestCase):
    def test_populates_pub_date_from_timestamp(self):
        episode = RssEpisode.from_ytdlp(
            {
                "id": "abc123",
                "title": "Sample Title",
                "timestamp": 1710806400,
            },
            "tester",
        )
        self.assertEqual(
            episode.pub_date,
            datetime.fromtimestamp(1710806400, tz=timezone.utc),
        )

    def test_populates_pub_date_from_upload_date(self):
        episode = RssEpisode.from_ytdlp(
            {
                "id": "def456",
                "title": "Sample Title",
                "upload_date": "20240319",
            },
            "tester",
        )
        self.assertEqual(
            episode.pub_date,
            datetime(2024, 3, 19, tzinfo=timezone.utc),
        )

    def test_missing_date_fields_keeps_pub_date_none(self):
        episode = RssEpisode.from_ytdlp(
            {
                "id": "ghi789",
                "title": "Sample Title",
            },
            "tester",
        )
        self.assertIsNone(episode.pub_date)


if __name__ == "__main__":
    unittest.main()
