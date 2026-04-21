import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from src.models import RssEpisode, YtDlpImage, YtDlpVideo


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


class TestYtDlpNestedModels(unittest.TestCase):
    def test_ytdlp_video_coerces_thumbnail_and_avatar_dicts(self):
        model = YtDlpVideo.model_validate(
            {
                "id": "abc123",
                "title": "Sample",
                "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
                "avatar": [{"url": "https://example.com/avatar.jpg"}],
                "postprocessors": [{"key": "FFmpegExtractAudio"}],
            }
        )

        self.assertIsNotNone(model.thumbnails)
        self.assertIsNotNone(model.avatar)
        self.assertIsInstance(model.thumbnails[0], YtDlpImage)
        self.assertIsInstance(model.avatar[0], YtDlpImage)
        assert model.thumbnails is not None
        self.assertEqual(model.thumbnails[0].url, "https://example.com/thumb.jpg")

    def test_rss_episode_from_typed_ytdlp_model(self):
        model = YtDlpVideo.model_validate(
            {
                "id": "typed1",
                "title": "Typed Video",
                "url": "https://youtube.com/watch?v=typed1",
                "timestamp": 1710806400,
            }
        )
        episode = RssEpisode.from_ytdlp(model, "tester")
        self.assertEqual(episode.id, "typed1")
        self.assertEqual(episode.title, "Typed Video")


if __name__ == "__main__":
    unittest.main()
