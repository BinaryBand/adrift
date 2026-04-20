import pytest

from src.app_common import (
    FeedSource,
    PodcastConfig,
    SourceFilter,
    ensure_feed_source,
    ensure_podcast_config,
    ensure_source_filter,
    parse_podcasts_raw,
)


def test_ensure_source_filter_from_dict() -> None:
    result = ensure_source_filter({"include": ["abc"], "exclude": ["def"]})
    assert isinstance(result, SourceFilter)
    assert result.include == ["abc"]
    assert result.exclude == ["def"]


def test_ensure_feed_source_from_dict() -> None:
    source = ensure_feed_source({"url": "https://example.com/feed.rss", "filters": {"r_rules": []}})
    assert isinstance(source, FeedSource)
    assert source.url == "https://example.com/feed.rss"
    assert isinstance(source.filters, SourceFilter)


def test_ensure_podcast_config_from_dict() -> None:
    podcast = ensure_podcast_config(
        {
            "name": "Demo",
            "references": [{"url": "https://example.com/ref.rss"}],
            "downloads": [{"url": "yt://@demo"}],
            "schedule": ["FREQ=WEEKLY;BYDAY=MO"],
        }
    )
    assert isinstance(podcast, PodcastConfig)
    assert podcast.name == "Demo"
    assert isinstance(podcast.references[0], FeedSource)
    assert isinstance(podcast.downloads[0], FeedSource)


def test_parse_podcasts_raw_mixed_entries() -> None:
    model = PodcastConfig(name="ModelEntry", path="/tmp/model-entry")
    parsed = parse_podcasts_raw([model, {"name": "DictEntry"}])
    assert [item.name for item in parsed] == ["ModelEntry", "DictEntry"]


def test_ensure_feed_source_rejects_invalid_type() -> None:
    with pytest.raises(TypeError):
        ensure_feed_source("not-a-source")  # type: ignore[arg-type]
