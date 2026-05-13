"""Normalize raw feedparser objects into typed domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from dateutil import parser
from feedparser import FeedParserDict

from adrift.models import RssChannel, RssEpisode
from adrift.utils.image import extract_image_from_feedparser
from adrift.utils.media import AUDIO_EXTENSIONS, parse_duration
from adrift.utils.regex import LINK_REGEX


def _getattr_multi(obj: object, *fields: str, default: object = "") -> object:
    for field in fields:
        value = getattr(obj, field, None)
        if value is not None:
            return value
    return default


def channel_from_feedparser(channel: FeedParserDict) -> RssChannel:
    """Convert a feedparser channel payload to a typed RssChannel."""
    return RssChannel(
        title=_pick_channel_field(channel, "title"),
        author=_pick_channel_field(channel, "author", "itunes_author", "creator"),
        subtitle=_pick_channel_field(channel, "subtitle", "itunes_subtitle"),
        url=_pick_channel_field(channel, "url"),
        description=_pick_channel_field(channel, "description", "summary"),
        image=_extract_image_url(channel),
    )


def episode_from_feedparser(entry: FeedParserDict) -> RssEpisode:
    """Convert a feedparser entry payload to a typed RssEpisode."""
    episode_id, title, author, description = _entry_basic_fields(entry)
    content = _extract_content_url(entry)
    if content is None:
        raise ValueError("No valid audio content URL found")

    return RssEpisode(
        id=episode_id,
        title=title,
        author=author,
        description=description,
        content=content,
        pub_date=entry_pub_date_from_feedparser(entry),
        duration=_parse_entry_duration(entry),
        image=_parse_entry_image(entry),
    )


def entry_title_from_feedparser(entry: FeedParserDict) -> str:
    """Return a normalized title string for feed entry filtering."""
    title = getattr(entry, "title", "")
    return str(title) if title is not None else ""


def entry_pub_date_from_feedparser(entry: FeedParserDict) -> datetime | None:
    """Return parsed publication date for schedule filtering."""
    return _parse_entry_pub_date(entry)


def _extract_image_url(channel: FeedParserDict) -> str:
    val = extract_image_from_feedparser(cast(object, channel.get("image")))
    if val:
        return val
    return extract_image_from_feedparser(cast(object, channel.get("itunes_image")))


def _pick_channel_field(channel: FeedParserDict, *names: str) -> str:
    for name in names:
        value = getattr(channel, name, None)
        if value:
            return str(value)
    return ""


def _entry_basic_fields(entry: FeedParserDict) -> tuple[str, str, str, str]:
    return (
        str(_getattr_multi(entry, "id", "guid", default="")),
        str(getattr(entry, "title", "")),
        str(_getattr_multi(entry, "author", "itunes_author", default="")),
        str(_getattr_multi(entry, "description", "summary", default="")),
    )


def _extract_content_url(entry: FeedParserDict) -> str | None:
    candidates = _collect_enclosure_strings(entry)
    audio_urls = _filter_audio_urls(candidates)
    return audio_urls[0] if audio_urls else None


def _collect_enclosure_strings(entry: FeedParserDict) -> list[str]:
    content = getattr(entry, "enclosures", [])
    if content:
        return _extract_urls_from_enclosures(content)

    url = _getattr_multi(entry, "url", default=None)
    if isinstance(url, str) and url:
        return [url]
    return []


def _extract_urls_from_enclosures(content: object) -> list[str]:
    urls: list[str] = []
    enclosures = cast(list[object], content) if isinstance(content, list) else []
    for enclosure in enclosures:
        urls.extend(LINK_REGEX.findall(_enclosure_value(enclosure)))
    return urls


def _enclosure_value(enclosure: object) -> str:
    if isinstance(enclosure, str):
        return enclosure

    getter = getattr(enclosure, "get", None)
    if not callable(getter):
        return ""

    href = getter("href", "")
    if isinstance(href, str):
        return href
    return ""


def _filter_audio_urls(urls: list[str]) -> list[str]:
    return [url for url in urls if any(url.lower().find(ext) != -1 for ext in AUDIO_EXTENSIONS)]


def _parse_entry_pub_date(entry: FeedParserDict) -> datetime | None:
    try:
        pub_date_str = _getattr_multi(entry, "published", "pubDate", default="")
        if not isinstance(pub_date_str, str):
            return None
        pub_date = parser.parse(pub_date_str)
        if pub_date.tzinfo is None:
            return pub_date.replace(tzinfo=timezone.utc)
        return pub_date
    except (ValueError, TypeError, AttributeError):
        return None


def _parse_entry_duration(entry: FeedParserDict) -> float | None:
    duration = getattr(entry, "itunes_duration", None)
    if duration is not None:
        return parse_duration(duration)
    return None


def _parse_entry_image(entry: FeedParserDict) -> str | None:
    image = _getattr_multi(entry, "itunes_image", "image", default=None)
    if image is None:
        return None
    if isinstance(image, str):
        return image
    getter = getattr(image, "get", None)
    if callable(getter):
        href = getter("href", None)
        if isinstance(href, str) and href:
            return href
        url = getter("url", None)
        if isinstance(url, str) and url:
            return url
    return None


__all__ = [
    "channel_from_feedparser",
    "episode_from_feedparser",
    "entry_pub_date_from_feedparser",
    "entry_title_from_feedparser",
]
