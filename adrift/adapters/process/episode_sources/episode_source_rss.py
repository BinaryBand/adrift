import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar, cast

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
from adrift.models import FeedSource, RssChannel, RssEpisode
from adrift.models.ports import EpisodeSourceFetchContext, EpisodeSourcePort
from adrift.utils.progress import Callback
from adrift.utils.regex import LINK_REGEX, re_compile
from adrift.utils.schedule import rrule_occurrence_exists

_RSS_HTTP_CACHE_PREFIX = "rss:http:"
_RSS_PARSED_CACHE_PREFIX = "rss:parsed:"
_RSS_HTTP_CACHE_TTL_SECONDS = 30 * 24 * 3600

T = TypeVar("T")


def _build_rss_cache() -> Cache:
    path = Path(".cache/rss").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return Cache(str(path))


_RSS_CACHE = _build_rss_cache()
_RSS_CACHE_WRAPPER = RaceAwareCacheWrapper(_RSS_CACHE)


def _cache_set_with_retry(cache: Cache, key: str, value: T, expire: int | None = None) -> None:
    if cache is _RSS_CACHE:
        _RSS_CACHE_WRAPPER.set(key, value, expire=expire)
        return
    RaceAwareCacheWrapper(cache).set(key, value, expire=expire)


def _rss_http_cache_key(
    rss_url: str,
    filter_value: str | None = None,
    r_rules: list[str] | None = None,
) -> str:
    if filter_value is None and r_rules is None:
        return f"{_RSS_HTTP_CACHE_PREFIX}{rss_url}"
    rules_key = ",".join(sorted(r_rules or []))
    filter_key = "" if filter_value is None else filter_value
    return f"{_RSS_HTTP_CACHE_PREFIX}{rss_url}:{filter_key}:{rules_key}"


def _load_cached_rss_payload(cache_key: str) -> dict[str, str] | None:
    cached = _RSS_CACHE.get(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("feed_str"), str):
        return cached
    return None


def _conditional_rss_headers(cached_payload: dict[str, str] | None) -> dict[str, str]:
    if cached_payload is None:
        return {}
    headers: dict[str, str] = {}
    etag = cached_payload.get("etag")
    if etag:
        headers["If-None-Match"] = etag
    last_modified = cached_payload.get("last_modified")
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _store_cached_rss_payload(cache_key: str, feed_str: str, headers: dict[str, str]) -> None:
    payload: dict[str, str] = {"feed_str": feed_str}
    etag = headers.get("ETag")
    if etag:
        payload["etag"] = etag
    last_modified = headers.get("Last-Modified")
    if last_modified:
        payload["last_modified"] = last_modified
    _cache_set_with_retry(_RSS_CACHE, cache_key, payload, expire=_RSS_HTTP_CACHE_TTL_SECONDS)


def _response_headers_dict(response: Any) -> dict[str, str]:
    raw_headers = getattr(response, "headers", None)
    if raw_headers is None:
        return {}
    items = getattr(raw_headers, "items", None)
    if not callable(items):
        return {}
    try:
        return {str(key): str(value) for key, value in items()}
    except TypeError:
        return {}


def _fetch_rss_feed_str(rss_url: str, cache_key: str | None = None) -> str:
    resolved_cache_key = cache_key or _rss_http_cache_key(rss_url)
    cached_payload = _load_cached_rss_payload(resolved_cache_key)
    response = requests.get(rss_url, timeout=15, headers=_conditional_rss_headers(cached_payload))
    if response.status_code == 304:
        if cached_payload is not None:
            return cached_payload["feed_str"]
        response = requests.get(rss_url, timeout=15)
    response.raise_for_status()
    feed_str = response.text
    _store_cached_rss_payload(resolved_cache_key, feed_str, _response_headers_dict(response))
    return feed_str


def get_rss_channel(rss_url: str) -> RssChannel:
    """Fetch and parse an RSS feed to extract channel information."""
    feed_str = _fetch_rss_feed_str(rss_url)
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


def _feed_fingerprint(feed_str: str) -> str:
    return hashlib.md5(feed_str.encode(), usedforsecurity=False).hexdigest()[:16]


def _parsed_episodes_cache_key(http_cache_key: str, feed_str: str) -> str:
    return f"{_RSS_PARSED_CACHE_PREFIX}{http_cache_key}:{_feed_fingerprint(feed_str)}"


def _load_cached_episodes(parsed_key: str) -> list[RssEpisode] | None:
    cached = _RSS_CACHE.get(parsed_key)
    return cached if isinstance(cached, list) else None


def _store_cached_episodes(parsed_key: str, episodes: list[RssEpisode]) -> None:
    _cache_set_with_retry(_RSS_CACHE, parsed_key, episodes, expire=_RSS_HTTP_CACHE_TTL_SECONDS)


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
    cache_key = _rss_http_cache_key(url, filter, r_rules)
    feed_str = _fetch_rss_feed_str(url, cache_key=cache_key)
    parsed_key = _parsed_episodes_cache_key(cache_key, feed_str)
    cached_episodes = _load_cached_episodes(parsed_key)
    if cached_episodes is not None:
        if callback:
            callback(len(cached_episodes), len(cached_episodes))
        return cached_episodes
    parsed = feedparser.parse(feed_str)
    raw_entries = getattr(parsed, "entries", [])
    entries_list = cast(list[FeedParserDict], raw_entries) if isinstance(raw_entries, list) else []
    entries = _filter_feed_entries(entries_list, filter, r_rules)
    episodes = _parse_feed_entries(entries, callback)
    _store_cached_episodes(parsed_key, episodes)
    return episodes


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
