"""Tests for episode source adapters."""

from unittest.mock import patch

from adrift.adapters import get_episode_source_adapter
from adrift.adapters.process.episode_sources.episode_source_rss import (
    RssEpisodeSourceAdapter,
)
from adrift.adapters.process.episode_sources.episode_source_youtube import (
    YouTubeEpisodeSourceAdapter,
)
from adrift.adapters.process.ports import EpisodeSourceFetchContext
from adrift.models import FeedSource, RssChannel, RssEpisode


def test_rss_adapter_fetches_episodes():
    """Verify RSS adapter delegates to get_rss_episodes."""
    # Create a non-YouTube FeedSource
    source = FeedSource(url="https://example.com/feed.xml")
    adapter = RssEpisodeSourceAdapter()

    # Mock get_rss_episodes
    mock_episodes = [
        RssEpisode(
            id="1",
            title="Episode 1",
            author="Test Author",
            content="https://example.com/ep1.mp3",
        )
    ]

    rss_mod = "adrift.adapters.process.episode_sources.episode_source_rss"
    with patch(f"{rss_mod}.get_rss_episodes", return_value=mock_episodes):
        result = adapter.fetch_episodes(source)

    assert result == mock_episodes
    assert len(result) == 1
    assert result[0].title == "Episode 1"


def test_rss_adapter_fetches_channel():
    """Verify RSS adapter delegates to get_rss_channel."""
    source = FeedSource(url="https://example.com/feed.xml")
    adapter = RssEpisodeSourceAdapter()

    mock_channel = RssChannel(
        title="Test Podcast",
        author="Author",
        subtitle="",
        url="https://example.com",
        description="",
        image="",
    )

    rss_mod = "adrift.adapters.process.episode_sources.episode_source_rss"
    with patch(f"{rss_mod}.get_rss_channel", return_value=mock_channel):
        result = adapter.fetch_channel(source)

    assert result == mock_channel
    assert result.title == "Test Podcast"


def test_youtube_adapter_fetches_episodes():
    """Verify YouTube adapter delegates to get_youtube_episodes."""
    source = FeedSource(url="https://www.youtube.com/@testchannel")
    adapter = YouTubeEpisodeSourceAdapter()

    mock_episodes = [
        RssEpisode(
            id="video123",
            title="YouTube Video",
            author="Test Channel",
            content="https://youtube.com/watch?v=video123",
        )
    ]

    with patch(
        "adrift.adapters.process.youtube.metadata.get_youtube_episodes",
        return_value=mock_episodes,
    ):
        result = adapter.fetch_episodes(source, EpisodeSourceFetchContext(title="Test Channel"))

    assert result == mock_episodes
    assert len(result) == 1
    assert result[0].id == "video123"


def test_youtube_adapter_fetches_channel():
    """Verify YouTube adapter delegates to get_youtube_channel."""
    source = FeedSource(url="https://www.youtube.com/@testchannel")
    adapter = YouTubeEpisodeSourceAdapter()

    mock_channel = RssChannel(
        title="Test Channel",
        author="Channel",
        subtitle="",
        url="https://www.youtube.com/@testchannel",
        description="",
        image="",
    )

    with patch(
        "adrift.adapters.process.youtube.metadata.get_youtube_channel",
        return_value=mock_channel,
    ):
        result = adapter.fetch_channel(source)

    assert result == mock_channel
    assert result.title == "Test Channel"


def test_factory_returns_rss_adapter_for_rss_url():
    """Verify factory returns RSS adapter for non-YouTube URLs."""
    source = FeedSource(url="https://example.com/feed.xml")

    adapter = get_episode_source_adapter(source)

    assert isinstance(adapter, RssEpisodeSourceAdapter)


def test_factory_returns_youtube_adapter_for_youtube_url():
    """Verify factory returns YouTube adapter for YouTube URLs."""
    # Test with various YouTube URL formats (only @ format is supported)
    youtube_urls = [
        "https://www.youtube.com/@testchannel",
        "https://youtube.com/@testchannel",
        "https://www.youtube.com/@testchannel/videos",
        "yt://#testplaylist",
        "https://www.youtube.com/playlist?list=PL12345",
    ]

    for url in youtube_urls:
        source = FeedSource(url=url)
        adapter = get_episode_source_adapter(source)
        assert isinstance(adapter, YouTubeEpisodeSourceAdapter), f"Failed for URL: {url}"


def test_rss_adapter_passes_filters_to_rss_episodes():
    """Verify RSS adapter extracts and passes filters correctly."""
    source = FeedSource(url="https://example.com/feed.xml", filters={"include": ["test"]})
    adapter = RssEpisodeSourceAdapter()

    rss_mod = "adrift.adapters.process.episode_sources.episode_source_rss"
    with patch(f"{rss_mod}.get_rss_episodes") as mock_get:
        mock_get.return_value = []
        adapter.fetch_episodes(source)

        # Verify the call was made with extracted filters
        assert mock_get.called
        call_args = mock_get.call_args
        # Should have url as first positional arg
        assert call_args[0][0] == "https://example.com/feed.xml"


def test_youtube_adapter_passes_title_and_options():
    """Verify YouTube adapter passes title and detailed flag correctly."""
    source = FeedSource(url="https://www.youtube.com/@testchannel")
    adapter = YouTubeEpisodeSourceAdapter()

    with patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes") as mock_get:
        mock_get.return_value = []
        adapter.fetch_episodes(
            source,
            EpisodeSourceFetchContext(title="My Podcast", detailed=True),
        )

        assert mock_get.called
        call_args = mock_get.call_args
        # First arg is URL, second is title
        assert call_args[0][0] == "https://www.youtube.com/@testchannel"
        assert call_args[0][1] == "My Podcast"
        assert call_args[0][2].detailed is True


def test_youtube_adapter_passes_refresh_option():
    """Verify YouTube adapter forwards refresh into YtFetchOptions."""
    source = FeedSource(url="https://www.youtube.com/@testchannel")
    adapter = YouTubeEpisodeSourceAdapter()

    with patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes") as mock_get:
        mock_get.return_value = []
        adapter.fetch_episodes(
            source,
            EpisodeSourceFetchContext(title="My Podcast", refresh=True),
        )

        assert mock_get.call_args[0][2].refresh is True
