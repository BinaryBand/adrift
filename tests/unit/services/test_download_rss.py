"""Tests for RSS feed regeneration, focused on the empty-feed clobber guard."""

import unittest
from unittest.mock import MagicMock, patch

from adrift.models import FeedSource, PodcastConfig, RssChannel
from adrift.services import download_rss


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Example Show",
        path="/tmp/example-show",
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="yt://@example-show")],
    )


def _channel() -> RssChannel:
    return RssChannel(
        title="Example Show",
        author="",
        subtitle="",
        url="",
        description="",
        image="https://img.example.com/cover.jpg",
    )


@patch.object(download_rss, "s3_prefix", return_value=("bucket", "media/podcasts/example"))
@patch.object(download_rss, "process_feeds", return_value=[])
@patch.object(download_rss, "_build_channel")
@patch.object(download_rss, "_match_to_s3")
@patch.object(download_rss, "podcast_to_rss", return_value="<rss/>")
@patch.object(download_rss, "_upload_rss")
class TestUpdateRssClobberGuard(unittest.TestCase):
    def test_skips_upload_when_no_episodes_matched(
        self, upload, _to_rss, match, build_channel, _feeds, _prefix
    ):
        build_channel.return_value = _channel()
        match.return_value = []  # transient fetch failure -> empty build

        download_rss.update_rss(_config(), MagicMock())

        upload.assert_not_called()

    def test_uploads_when_episodes_present(
        self, upload, _to_rss, match, build_channel, _feeds, _prefix
    ):
        build_channel.return_value = _channel()
        match.return_value = [MagicMock()]  # at least one matched episode

        download_rss.update_rss(_config(), MagicMock())

        upload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
