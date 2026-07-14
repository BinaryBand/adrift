import unittest
from datetime import UTC, datetime

from adrift.adapters.process.youtube.normalizer import rss_episode_from_ytdlp
from adrift.core.models import YtDlpImage, YtDlpVideo


class TestRssEpisodeFromYtdlp(unittest.TestCase):
    def test_populates_pub_date_from_timestamp(self):
        episode = rss_episode_from_ytdlp(
            {
                "id": "abc123",
                "title": "Sample Title",
                "timestamp": 1710806400,
            },
            "tester",
        )
        assert episode.pub_date == datetime.fromtimestamp(1710806400, tz=UTC)

    def test_populates_pub_date_from_upload_date(self):
        episode = rss_episode_from_ytdlp(
            {
                "id": "def456",
                "title": "Sample Title",
                "upload_date": "20240319",
            },
            "tester",
        )
        assert episode.pub_date == datetime(2024, 3, 19, tzinfo=UTC)

    def test_missing_date_fields_keeps_pub_date_none(self):
        episode = rss_episode_from_ytdlp(
            {
                "id": "ghi789",
                "title": "Sample Title",
            },
            "tester",
        )
        assert episode.pub_date is None


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

        assert model.thumbnails is not None
        assert model.avatar is not None
        assert isinstance(model.thumbnails[0], YtDlpImage)
        assert isinstance(model.avatar[0], YtDlpImage)
        assert model.thumbnails is not None
        assert model.thumbnails[0].url == "https://example.com/thumb.jpg"

    def test_rss_episode_from_typed_ytdlp_model(self):
        model = YtDlpVideo.model_validate(
            {
                "id": "typed1",
                "title": "Typed Video",
                "url": "https://youtube.com/watch?v=typed1",
                "timestamp": 1710806400,
            }
        )
        episode = rss_episode_from_ytdlp(model, "tester")
        assert episode.id == "typed1"
        assert episode.title == "Typed Video"


if __name__ == "__main__":
    unittest.main()
