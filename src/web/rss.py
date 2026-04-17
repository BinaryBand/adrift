import functools
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import feedparser
import requests
from dateutil import parser
from dateutil.rrule import rrulestr
from diskcache import Cache
from feedparser import FeedParserDict

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.models import RssChannel, RssEpisode
from src.utils.progress import Callback
from src.utils.regex import LINK_REGEX, re_compile

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".mp4", ".opus"}


@functools.cache
def _rss_cache() -> Cache:
    """Get the RSS feed cache instance."""
    return Cache(".cache/rss")


def _extract_image_url(channel: FeedParserDict) -> str:
    """Thin wrapper to keep a small replaceable root for image extraction."""
    return _extract_image_url_impl(channel)


def _extract_image_url_impl(channel: FeedParserDict) -> str:
    """Extract image URL from various possible locations in the feed.

    Prefer the first non-empty candidate.
    """
    val = _extract_image_from(channel.get("image"))
    if val:
        return val
    val = _extract_image_from(channel.get("itunes_image"))
    if val:
        return val
    return ""


def _extract_image_from(obj: object) -> str:
    # Try string-like
    res = _extract_image_from_str(obj)
    if res:
        return res
    # Try mapping-like objects with .get
    res = _extract_image_from_get(obj)
    if res:
        return res
    # Try attribute access
    res = _extract_image_from_attrs(obj)
    if res:
        return res
    return ""


def _extract_image_from_str(obj: object) -> str:
    if isinstance(obj, str) and obj:
        return obj
    return ""


def _extract_image_from_get(obj: object) -> str:
    get = getattr(obj, "get", None)
    if not callable(get):
        return ""
    for key in ("href", "url"):
        val = get(key, None)
        if isinstance(val, str) and val:
            return val
    return ""


def _extract_image_from_attrs(obj: object) -> str:
    href = getattr(obj, "href", None)
    if isinstance(href, str) and href:
        return href
    url = getattr(obj, "url", None)
    if isinstance(url, str) and url:
        return url
    return ""


def parse_duration(duration_str: str | None) -> float | None:
    """Parse duration string in HH:MM:SS or MM:SS format to total seconds."""
    if duration_str is None or duration_str == "":
        return None

    parts = duration_str.split(":")
    weights_map: dict[int, tuple[int, ...]] = {
        1: (1,),
        2: (60, 1),
        3: (3600, 60, 1),
    }
    weights = weights_map.get(len(parts))
    if weights is None:
        print(f"WARNING: Unrecognized duration format: {duration_str}")
        return None
    return sum(weight * float(part) for weight, part in zip(weights, parts))


def get_rss_channel(rss_url: str) -> RssChannel:
    """Fetch and parse an RSS feed from a URL to extract channel information."""
    feed_str = _fetch_channel_feed_str(rss_url)

    feed: FeedParserDict = feedparser.parse(feed_str)
    if feed.bozo and hasattr(feed, "bozo_exception"):
        issue = feed.get("bozo_exception")
        print(f"WARNING: RSS feed may have issues: {issue}")

    channel: FeedParserDict = feed.feed
    return RssChannel(
        title=_pick_channel_field(channel, "title"),
        author=_pick_channel_field(channel, "author", "itunes_author", "creator"),
        subtitle=_pick_channel_field(channel, "subtitle", "itunes_subtitle"),
        url=_pick_channel_field(channel, "url"),
        description=_pick_channel_field(channel, "description", "summary"),
        image=_extract_image_url(channel),
    )


def _fetch_channel_feed_str(rss_url: str) -> str:
    cache_key = f"rss:{rss_url}"
    feed_str: str | None = _rss_cache().get(cache_key)
    if feed_str is None:
        response = requests.get(rss_url, timeout=15)
        feed_str = response.text
        _rss_cache().set(cache_key, feed_str, expire=3600)
    return feed_str


def _pick_channel_field(channel: FeedParserDict, *names: str) -> str:
    for n in names:
        v = getattr(channel, n, None)
        if v:
            return v
    return ""


def _extract_content_url(entry: FeedParserDict) -> str | None:
    """Extract content URL from entry enclosures or url."""
    candidates = _collect_enclosure_strings(entry)
    audio_urls = _filter_audio_urls(candidates)
    return audio_urls[0] if audio_urls else None


def _collect_enclosure_strings(entry: FeedParserDict) -> list[str]:
    content = getattr(entry, "enclosures", [])
    if content:
        return _extract_urls_from_enclosures(content)

    url = getattr(entry, "url", None)
    if isinstance(url, str) and url:
        return [url]
    return []


def _extract_urls_from_enclosures(content: object) -> list[str]:
    urls: list[str] = []
    enclosures = cast(list[object], content) if isinstance(content, list) else []
    for enc in enclosures:
        urls.extend(LINK_REGEX.findall(_enclosure_value(enc)))
    return urls


def _enclosure_value(enc: object) -> str:
    if isinstance(enc, str):
        return enc

    get = getattr(enc, "get", None)
    if not callable(get):
        return ""

    href = get("href", "")
    if isinstance(href, str):
        return href
    return ""


def _filter_audio_urls(urls: list[str]) -> list[str]:
    return [u for u in urls if any(u.lower().find(ext) != -1 for ext in AUDIO_EXTENSIONS)]


def parse_rss_entry(entry: FeedParserDict) -> RssEpisode:
    """Parse a single RSS feed entry to extract episode information."""
    id, title, author, description = _entry_basic_fields(entry)

    content = _extract_content_url(entry)
    assert content is not None, "No valid audio content URL found"

    pub_date = _parse_entry_pub_date(entry)

    duration = _parse_entry_duration(entry)

    image = _parse_entry_image(entry)

    return RssEpisode(
        id=id,
        title=title,
        author=author,
        description=description,
        content=content,
        pub_date=pub_date,
        duration=duration,
        image=image,
    )


def _entry_basic_fields(entry: FeedParserDict) -> tuple[str, str, str, str]:
    return (
        getattr(entry, "id", getattr(entry, "guid", "")),
        getattr(entry, "title", ""),
        getattr(entry, "author", getattr(entry, "itunes_author", "")),
        getattr(entry, "description", getattr(entry, "summary", "")),
    )


def _parse_entry_duration(entry: FeedParserDict) -> float | None:
    duration = getattr(entry, "itunes_duration", None)
    if duration is not None:
        return parse_duration(duration)
    return None


def _parse_entry_image(entry: FeedParserDict) -> str | None:
    image = getattr(entry, "itunes_image", getattr(entry, "image", None))
    if image is not None and not isinstance(image, str):
        return image.get("href", None) or image.get("url", None)
    return image


def _align_to_tzinfo(dt: datetime, reference: datetime) -> datetime:
    if reference.tzinfo is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=reference.tzinfo)
    if reference.tzinfo is None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _build_rrule(rule_str: str, day_start: datetime, day_end: datetime):
    if "DTSTART" not in rule_str.upper():
        return rrulestr(rule_str, dtstart=day_start), day_start, day_end
    rule = rrulestr(rule_str)
    ref = getattr(rule, "_dtstart", None)
    if isinstance(ref, datetime):
        day_start = _align_to_tzinfo(day_start, ref)
        day_end = _align_to_tzinfo(day_end, ref)
    return rule, day_start, day_end


def _rrule_has_occurrence_on_date(pub_date: datetime, rule_str: str) -> bool:
    """Return True if the RFC 5545 RRULE produces an occurrence on pub_date's calendar day."""
    day_start = datetime.combine(pub_date.date(), datetime.min.time())
    day_end = day_start + timedelta(days=1)
    return _rrule_occurrence_exists(rule_str, day_start, day_end)


def _rrule_occurrence_exists(rule_str: str, day_start: datetime, day_end: datetime) -> bool:
    try:
        rule, day_start, day_end = _build_rrule(rule_str, day_start, day_end)
        occ = rule.after(day_start - timedelta(microseconds=1), inc=True)
        if occ is None:
            return False
        return occ < _align_to_tzinfo(day_end, occ)
    except Exception:
        return False


def get_rss_episodes(
    url: str,
    filter: str | None = "",
    r_rules: list[str] | None = None,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Parse RSS feed and extract episode information for a podcast."""
    assert LINK_REGEX.match(url), "Invalid RSS feed url or file path"
    r_rules = r_rules or []
    r_rules_key = ",".join(sorted(r_rules))
    cache_key = f"feed:{url}:{filter}:{r_rules_key}"
    feed_str: str | None = _rss_cache().get(cache_key)
    if feed_str is None:
        response = requests.get(url, timeout=15)
        feed_str = response.text
        _rss_cache().set(cache_key, feed_str, 1800)
    entries = _filter_feed_entries(feedparser.parse(feed_str).entries, filter, r_rules)
    return _parse_feed_entries(entries, callback)


def _filter_feed_entries(
    entries: list[FeedParserDict],
    filter_value: str | None,
    r_rules: list[str],
) -> list[FeedParserDict]:
    filtered_entries = _apply_title_filter(entries, filter_value)
    return _apply_r_rules_filter(filtered_entries, r_rules)


def _apply_title_filter(
    entries: list[FeedParserDict], filter_value: str | None
) -> list[FeedParserDict]:
    if not filter_value:
        return entries
    regex = re_compile(filter_value)
    return [entry for entry in entries if regex.search(getattr(entry, "title"))]


def _apply_r_rules_filter(
    entries: list[FeedParserDict], r_rules: list[str]
) -> list[FeedParserDict]:
    if not r_rules:
        return entries
    return [entry for entry in entries if _entry_matches_any_r_rule(entry, r_rules)]


def _entry_matches_any_r_rule(entry: FeedParserDict, r_rules: list[str]) -> bool:
    pub_date = _parse_entry_pub_date(entry)
    if pub_date is None:
        return False
    return any(_rrule_has_occurrence_on_date(pub_date, rule) for rule in r_rules)


def _parse_entry_pub_date(entry: FeedParserDict) -> datetime | None:
    try:
        pub_date_str = getattr(entry, "published", getattr(entry, "pubDate", ""))
        pub_date = parser.parse(pub_date_str)
        if pub_date.tzinfo is None:
            return pub_date.replace(tzinfo=timezone.utc)
        return pub_date
    except (ValueError, TypeError, AttributeError):
        return None


def _parse_feed_entries(
    entries: list[FeedParserDict], callback: Callback | None = None
) -> list[RssEpisode]:
    total = len(entries)
    episodes: list[RssEpisode] = []
    for idx, entry in enumerate(entries):
        episodes.append(parse_rss_entry(entry))
        if callback:
            callback(idx + 1, total)
    return episodes
