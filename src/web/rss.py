import shutil
import uuid
from feedparser import FeedParserDict
from urllib.parse import urljoin
from datetime import datetime, timezone
from dateutil import parser
from xml.dom import minidom
from diskcache import Cache
from pathlib import Path

import xml.etree.ElementTree as ET
import feedparser
import functools
import mimetypes
import requests
import tempfile
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import AUDIO_EXTENSIONS, parse_duration
from src.files.images import make_square_image
from src.files.s3 import S3_ENDPOINT, exists, upload_file
from src.utils.progress import Callback
from src.utils.regex import LINK_REGEX, re_compile
from src.utils.text import create_slug, remove_control_chars
from src.models import RssChannel, RssEpisode


@functools.cache
def _rss_cache() -> Cache:
    """Get the RSS feed cache instance."""
    return Cache(".cache/rss")


def upload_thumbnail(thumbnail_url: str, author: str, id: str) -> str | None:
    """Top-level wrapper that runs the thumbnail upload pipeline.

    Keeps a small, replaceable root so the heavy-lifting lives in testable
    helpers below.
    """
    try:
        return _upload_thumbnail_pipeline(thumbnail_url, author, id)
    except Exception as e:
        print(f"WARNING: Failed to upload thumbnail for {id}: {e}")
        return None


def _existing_thumbnail_s3_path(path_base: Path, image_path: str) -> str | None:
    """Return a public URL for an existing thumbnail, or None."""
    existing_file = exists("media", image_path, True)
    if not existing_file:
        return None
    s3_path = (Path("media") / path_base / existing_file).as_posix()
    return urljoin(S3_ENDPOINT, s3_path)


def _download_thumbnail_bytes(
    thumbnail_url: str, timeout: int = 30
) -> tuple[bytes, str]:
    resp = requests.get(thumbnail_url, timeout=timeout)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    return resp.content, content_type


def _ext_for_content_type(content_type: str) -> str | None:
    ext = mimetypes.guess_extension(content_type) or ".bin"
    if ext in {".bin", ""}:
        return None
    return ext


def _stage_thumbnail_bytes(data: bytes, id: str, ext: str) -> Path:
    """Write bytes to a temporary file, make it square, and return Path."""
    temp_dir = tempfile.mkdtemp()
    staging_file = Path(temp_dir) / f"{create_slug(id)}{ext}"
    with open(staging_file, "wb") as f:
        f.write(data)
    make_square_image(staging_file)
    return staging_file


def _upload_thumbnail_pipeline(thumbnail_url: str, author: str, id: str) -> str | None:
    """Pipeline implementation for thumbnail upload (replaceable stages)."""
    author_slug = create_slug(author)
    path_base = Path(f"podcasts/{author_slug}/thumbnails")
    image_path = (path_base / id).as_posix()

    existing = _existing_thumbnail_s3_path(path_base, image_path)
    if existing:
        return existing

    data, content_type = _download_thumbnail_bytes(thumbnail_url)
    ext = _ext_for_content_type(content_type)
    if ext is None:
        return None

    staging_file = _stage_thumbnail_bytes(data, id, ext)
    return upload_file("media", f"{image_path}{ext}", staging_file)


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
    href = get("href", None)
    if href:
        return href
    url = get("url", None)
    if url:
        return url
    return ""


def _extract_image_from_attrs(obj: object) -> str:
    href = getattr(obj, "href", None)
    if href:
        return href
    url = getattr(obj, "url", None)
    if url:
        return url
    return ""


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
        return sum(
            (
                LINK_REGEX.findall(enc if isinstance(enc, str) else enc.get("href", ""))
                for enc in content
            ),
            [],
        )
    if hasattr(entry, "url"):
        return [entry.get("url", "")]
    return []


def _filter_audio_urls(urls: list[str]) -> list[str]:
    return [
        u for u in urls if any(u.lower().find(ext) != -1 for ext in AUDIO_EXTENSIONS)
    ]


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


def _day_of_week_to_int(dow: str) -> int:
    """Convert day of week string to integer (0=Mon, 6=Sun).

    Accepts three-letter abbreviations or full names, case-insensitive.
    """
    if not isinstance(dow, str):
        raise ValueError("Invalid day of week")

    dow_short = dow.strip().lower()[:3]
    dow_map = {
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
    }
    if dow_short not in dow_map:
        raise ValueError(f"Invalid day of week: {dow}")
    return dow_map[dow_short]


def get_rss_episodes(
    url: str,
    filter: str | None = "",
    feed_day_of_week_filter: list[str] | None = None,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Parse RSS feed and extract episode information for a podcast."""
    assert LINK_REGEX.match(url), "Invalid RSS feed url or file path"
    normalized_days = _normalize_day_filters(feed_day_of_week_filter)
    feed_str = _load_rss_feed_text(url, filter, normalized_days)
    entries = _filter_feed_entries(
        feedparser.parse(feed_str).entries, filter, normalized_days
    )
    return _parse_feed_entries(entries, callback)


def _normalize_day_filters(feed_day_of_week_filter: list[str] | None) -> list[str]:
    if not feed_day_of_week_filter:
        return []
    return [day.strip().lower()[:3] for day in feed_day_of_week_filter]


def _load_rss_feed_text(
    url: str, filter_value: str | None, normalized_days: list[str]
) -> str:
    dow_filter_key = ",".join(sorted(normalized_days)) if normalized_days else ""
    cache_key = f"feed:{url}:{filter_value}:{dow_filter_key}"
    feed_str: str | None = _rss_cache().get(cache_key)
    if feed_str is not None:
        return feed_str

    response = requests.get(url, timeout=15)
    feed_str = response.text
    _rss_cache().set(cache_key, feed_str, 1800)
    return feed_str


def _filter_feed_entries(
    entries: list[FeedParserDict],
    filter_value: str | None,
    normalized_days: list[str],
) -> list[FeedParserDict]:
    filtered_entries = _apply_title_filter(entries, filter_value)
    return _apply_day_filter(filtered_entries, normalized_days)


def _apply_title_filter(
    entries: list[FeedParserDict], filter_value: str | None
) -> list[FeedParserDict]:
    if not filter_value:
        return entries
    regex = re_compile(filter_value)
    return [entry for entry in entries if regex.search(getattr(entry, "title"))]


def _apply_day_filter(
    entries: list[FeedParserDict], normalized_days: list[str]
) -> list[FeedParserDict]:
    if not normalized_days:
        return entries
    allowed_days = {_day_of_week_to_int(day) for day in normalized_days}
    return [entry for entry in entries if _entry_weekday(entry) in allowed_days]


def _entry_weekday(entry: FeedParserDict) -> int:
    pub_date = _parse_entry_pub_date(entry)
    if pub_date is None:
        return -1
    return pub_date.weekday()


def _parse_entry_pub_date(entry: FeedParserDict) -> datetime | None:
    try:
        pub_date_str = getattr(entry, "published", getattr(entry, "pubDate", ""))
        pub_date = parser.parse(pub_date_str)
        if pub_date is not None and pub_date.tzinfo is None:
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


def podcast_to_rss(channel: RssChannel, episodes: list[RssEpisode]) -> str:
    rss = _build_rss_root()
    channel_elem = ET.SubElement(rss, "channel")
    _append_channel_metadata(channel_elem, channel)
    for episode in episodes:
        _append_episode_item(channel_elem, episode)
    return _serialize_rss(rss)


def _build_rss_root() -> ET.Element:
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    return rss


def _set_text_element(parent: ET.Element, tag: str, value: str | None) -> None:
    if value:
        ET.SubElement(parent, tag).text = value


def _append_channel_metadata(channel_elem: ET.Element, channel: RssChannel) -> None:
    _set_text_element(channel_elem, "title", channel.title)
    _set_text_element(channel_elem, "itunes:author", channel.author)
    _set_text_element(channel_elem, "url", channel.url)
    _set_text_element(channel_elem, "description", channel.description)
    _set_text_element(channel_elem, "itunes:subtitle", channel.subtitle)
    _append_channel_image(channel_elem, channel)


def _append_channel_image(channel_elem: ET.Element, channel: RssChannel) -> None:
    if not channel.image:
        return
    ET.SubElement(channel_elem, "itunes:image", href=channel.image)
    image_elem = ET.SubElement(channel_elem, "image")
    ET.SubElement(image_elem, "url").text = channel.image
    ET.SubElement(image_elem, "title").text = channel.title or ""
    ET.SubElement(image_elem, "url").text = channel.url or ""


def _append_episode_item(channel_elem: ET.Element, episode: RssEpisode) -> None:
    item = ET.SubElement(channel_elem, "item")
    _set_text_element(item, "guid", episode.id)
    _set_text_element(item, "title", _safe_episode_title(episode))
    _set_text_element(item, "description", episode.description)
    _set_text_element(item, "itunes:author", episode.author)
    _append_episode_pub_date(item, episode)
    _append_episode_duration(item, episode)
    _append_episode_enclosure(item, episode)
    _append_episode_image(item, episode)


def _safe_episode_title(episode: RssEpisode) -> str | None:
    if not episode.title:
        return None
    return remove_control_chars(episode.title)


def _append_episode_pub_date(item: ET.Element, episode: RssEpisode) -> None:
    if isinstance(episode.pub_date, datetime):
        ET.SubElement(item, "pubDate").text = episode.pub_date.isoformat()


def _append_episode_duration(item: ET.Element, episode: RssEpisode) -> None:
    if episode.duration is not None:
        ET.SubElement(item, "itunes:duration").text = str(int(episode.duration))


def _append_episode_enclosure(item: ET.Element, episode: RssEpisode) -> None:
    if not episode.content:
        return
    content_type, _ = mimetypes.guess_type(episode.content)
    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", episode.content)
    enclosure.set("type", content_type or "audio/mpeg")


def _append_episode_image(item: ET.Element, episode: RssEpisode) -> None:
    if episode.image is not None and LINK_REGEX.match(episode.image):
        ET.SubElement(item, "itunes:image", href=episode.image)


def _serialize_rss(rss: ET.Element) -> str:
    rough_string = ET.tostring(rss, "utf-8")
    re_parsed = minidom.parseString(rough_string)
    return re_parsed.toprettyxml(indent="\t")


def download_direct(url: str, dest: Path) -> tuple[Path, bool]:
    """Download from direct HTTP source."""
    headers = _browser_headers_for(url)

    # Stream with a timeout and write to a temporary staging file
    with requests.get(url, stream=True, headers=headers, timeout=60) as response:
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(content_type) or ".mp3"

        dest.mkdir(parents=True, exist_ok=True)
        staging_file = dest / f"{uuid.uuid4().hex}{ext}"

        response.raw.decode_content = True
        with open(staging_file, "wb") as f:
            shutil.copyfileobj(response.raw, f)

    return staging_file, False


def _browser_headers_for(url: str) -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Encoding": "identity, deflate, br",
        "Connection": "keep-alive",
        "Referer": url,
    }
