from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import feedparser
import requests
from diskcache import Cache
from feedparser import FeedParserDict

from adrift.adapters.process.cache_retry import RaceAwareCacheWrapper
from adrift.adapters.process.episode_sources.rss_normalizer import (
    channel_from_feedparser,
    entry_pub_date_from_feedparser,
    entry_title_from_feedparser,
    episode_from_feedparser,
)
from adrift.adapters.process.ports import EpisodeSourceFetchContext, EpisodeSourcePort
from adrift.models import FeedSource, RssChannel, RssEpisode
from adrift.utils.progress import Callback
from adrift.utils.regex import LINK_REGEX, re_compile
from adrift.utils.schedule import rrule_occurrence_exists


def _build_rss_cache() -> Cache:
    path = Path(".cache/rss").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return Cache(str(path))


_RSS_CACHE = _build_rss_cache()
_RSS_CACHE_WRAPPER = RaceAwareCacheWrapper(_RSS_CACHE)


def _cache_set_with_retry(cache: Cache, key: str, value: str, expire: int | None = None) -> None:
    if cache is _RSS_CACHE:
        _RSS_CACHE_WRAPPER.set(key, value, expire=expire)
        return
    RaceAwareCacheWrapper(cache).set(key, value, expire=expire)


def _fetch_channel_feed_str(rss_url: str) -> str:
    cache_key = f"rss:{rss_url}"
    cached = _RSS_CACHE.get(cache_key)
    feed_str: str | None = cached if isinstance(cached, str) else None
    if feed_str is None:
        response = requests.get(rss_url, timeout=15)
        feed_str = response.text
        _cache_set_with_retry(_RSS_CACHE, cache_key, feed_str, expire=3600)
    return feed_str


def get_rss_channel(rss_url: str) -> RssChannel:
    """Fetch and parse an RSS feed to extract channel information."""
    feed_str = _fetch_channel_feed_str(rss_url)
    feed: FeedParserDict = feedparser.parse(feed_str)
    if feed.bozo and hasattr(feed, "bozo_exception"):
        issue = feed.get("bozo_exception")
        print(f"WARNING: RSS feed may have issues: {issue}")
    return channel_from_feedparser(feed.feed)


def _rrule_has_occurrence_on_date(pub_date: datetime, rule_str: str) -> bool:
    day_start = datetime.combine(pub_date.date(), datetime.min.time())
    day_end = day_start + timedelta(days=1)
    return rrule_occurrence_exists(rule_str, day_start, day_end)


def _filter_feed_entries(
    entries: list[FeedParserDict],
    filter_value: str | None,
    r_rules: list[str],
) -> list[FeedParserDict]:
    filtered = _apply_title_filter(entries, filter_value)
    return _apply_r_rules_filter(filtered, r_rules)


def _apply_title_filter(
    entries: list[FeedParserDict], filter_value: str | None
) -> list[FeedParserDict]:
    if not filter_value:
        return entries
    regex = re_compile(filter_value)
    return [entry for entry in entries if regex.search(entry_title_from_feedparser(entry))]


def _apply_r_rules_filter(
    entries: list[FeedParserDict], r_rules: list[str]
) -> list[FeedParserDict]:
    if not r_rules:
        return entries
    return [entry for entry in entries if _entry_matches_any_r_rule(entry, r_rules)]


def _entry_matches_any_r_rule(entry: FeedParserDict, r_rules: list[str]) -> bool:
    pub_date = entry_pub_date_from_feedparser(entry)
    if pub_date is None:
        return False
    return any(_rrule_has_occurrence_on_date(pub_date, rule) for rule in r_rules)


def _parse_feed_entries(
    entries: list[FeedParserDict], callback: Callback | None = None
) -> list[RssEpisode]:
    total = len(entries)
    episodes: list[RssEpisode] = []
    for idx, entry in enumerate(entries):
        episodes.append(episode_from_feedparser(entry))
        if callback:
            callback(idx + 1, total)
    return episodes


def get_rss_episodes(
    url: str,
    filter: str | None = "",
    r_rules: list[str] | None = None,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Parse RSS feed and extract episode information for a podcast."""
    if not LINK_REGEX.match(url):
        raise ValueError("Invalid RSS feed url or file path")
    r_rules = r_rules or []
    r_rules_key = ",".join(sorted(r_rules))
    cache_key = f"feed:{url}:{filter}:{r_rules_key}"
    feed_str: str | None = _RSS_CACHE.get(cache_key)
    if feed_str is None:
        response = requests.get(url, timeout=15)
        feed_str = response.text
        _cache_set_with_retry(_RSS_CACHE, cache_key, feed_str, 1800)
    parsed = feedparser.parse(feed_str)
    raw_entries = getattr(parsed, "entries", [])
    entries_list = cast(list[FeedParserDict], raw_entries) if isinstance(raw_entries, list) else []
    entries = _filter_feed_entries(entries_list, filter, r_rules)
    return _parse_feed_entries(entries, callback)


class RssEpisodeSourceAdapter(EpisodeSourcePort):
    """Adapter for fetching episodes from RSS feeds."""

    def fetch_episodes(
        self,
        source: FeedSource,
        context: EpisodeSourceFetchContext | None = None,
    ) -> list[RssEpisode]:
        """Fetch episodes from an RSS feed."""
        resolved_context = context or EpisodeSourceFetchContext()
        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for RSS episode fetching")

        filter_regex = source.filters.to_regex() if source.filters else None
        r_rules = source.filters.r_rules if source.filters else None
        return get_rss_episodes(url, filter_regex, r_rules, resolved_context.callback)

    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Fetch channel metadata from an RSS feed."""
        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for RSS channel fetching")
        return get_rss_channel(url)
