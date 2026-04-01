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
import pandas as pd
import requests
import tempfile
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.app_common import DAY_OF_WEEK
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
    """Download the remote thumbnail, make it square, upload to S3 and return the final URL."""
    try:
        author_slug = create_slug(author)
        path_base = Path(f"podcasts/{author_slug}/thumbnails")
        image_path = (path_base / id).as_posix()

        existing_file = exists("media", image_path, True)
        if existing_file:
            return urljoin(
                S3_ENDPOINT, ("media" / path_base / existing_file).as_posix()
            )

        print(f"Uploading thumbnail for {id} from {thumbnail_url}")

        response = requests.get(thumbnail_url, timeout=30)
        content_type = response.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(content_type) or ".bin"
        if ext in {".bin", ""}:
            print(
                f"WARNING: Unrecognised Content-Type for thumbnail {id}: {content_type!r}"
            )
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            staging_file = Path(temp_dir) / f"{create_slug(id)}{ext}"
            with open(staging_file, "wb") as f:
                f.write(response.content)

            make_square_image(staging_file)
            return upload_file("media", f"{image_path}{ext}", staging_file)

    except Exception as e:
        print(f"WARNING: Failed to upload thumbnail for {id}: {e}")
        return None


def _extract_image_url(channel: FeedParserDict) -> str:
    """Extract image URL from various possible locations in the feed"""
    if hasattr(channel, "image") and hasattr(channel.get("image"), "href"):
        assert isinstance(channel.get("image", {}).get("href"), str)
        return channel.get("image", {}).get("href")
    elif hasattr(channel, "image") and hasattr(channel.get("image"), "url"):
        assert isinstance(channel.get("image", {}).get("url"), str)
        return channel.get("image", {}).get("url")
    elif hasattr(channel, "itunes_image"):
        assert isinstance(channel.get("itunes_image"), str)
        return channel.get("itunes_image", "")
    return ""


def get_rss_channel(rss_url: str) -> RssChannel:
    """Fetch and parse an RSS feed from a URL to extract channel information."""
    cache_key = f"rss:{rss_url}"
    feed_str: str | None = _rss_cache().get(cache_key)
    if feed_str is None:
        response = requests.get(rss_url, timeout=15)
        feed_str = response.text
        _rss_cache().set(cache_key, feed_str, expire=3600)  # Cache for 1 hour

    feed: FeedParserDict = feedparser.parse(feed_str)
    if feed.bozo and hasattr(feed, "bozo_exception"):
        issue = feed.get("bozo_exception")
        print(f"WARNING: RSS feed may have issues: {issue}")

    channel: FeedParserDict = feed.feed
    return RssChannel(
        title=getattr(channel, "title", ""),
        author=getattr(channel, "author", "")
        or getattr(channel, "itunes_author", "")
        or getattr(channel, "creator", ""),
        subtitle=getattr(channel, "subtitle", "")
        or getattr(channel, "itunes_subtitle", ""),
        url=getattr(channel, "url", ""),
        description=getattr(channel, "description", "")
        or getattr(channel, "summary", ""),
        image=_extract_image_url(channel),
    )


def _extract_content_url(entry: FeedParserDict) -> str | None:
    """Extract content URL from entry enclosures or url."""
    content = getattr(entry, "enclosures", [])
    content_urls = []
    if content and len(content) > 0:
        for enc in content:
            string = enc if isinstance(enc, str) else enc.get("href", "")
            links = LINK_REGEX.findall(string)
            content_urls.extend(links)
    elif hasattr(entry, "url"):
        content_urls.append(entry.get("url", ""))

    content_urls = [
        url
        for url in content_urls
        if any(url.lower().find(ext) != -1 for ext in AUDIO_EXTENSIONS)
    ]
    return content_urls[0] if len(content_urls) > 0 else None


def parse_rss_entry(entry: FeedParserDict) -> RssEpisode:
    """Parse a single RSS feed entry to extract episode information."""
    id = getattr(entry, "id", getattr(entry, "guid", ""))
    title = getattr(entry, "title", "")
    author = getattr(entry, "author", getattr(entry, "itunes_author", ""))
    description = getattr(entry, "description", getattr(entry, "summary", ""))

    content = _extract_content_url(entry)
    assert content is not None, "No valid audio content URL found"

    pub_date_str = getattr(entry, "published", getattr(entry, "pubDate", ""))
    pub_date = parser.parse(pub_date_str)
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)

    duration = getattr(entry, "itunes_duration", None)
    if duration is not None:
        duration = parse_duration(duration)

    image = getattr(entry, "itunes_image", getattr(entry, "image", None))
    if image is not None and not isinstance(image, str):
        image = image.get("href", None) or image.get("url", None)

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
    feed_day_of_week_filter: list[DAY_OF_WEEK] | None = None,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Parse RSS feed and extract episode information for a podcast."""
    assert LINK_REGEX.match(url), "Invalid RSS feed url or file path"

    # Normalize day strings (case- and format-insensitive) and build cache key
    normalized_days: list[str] = []
    if feed_day_of_week_filter:
        normalized_days = [d.strip().lower()[:3] for d in feed_day_of_week_filter]
    dow_filter_key = ",".join(sorted(normalized_days)) if normalized_days else ""
    cache_key = f"feed:{url}:{filter}:{dow_filter_key}"
    feed_str: str | None = _rss_cache().get(cache_key)
    if feed_str is None:
        response = requests.get(url, timeout=15)
        feed_str = response.text
        _rss_cache().set(cache_key, feed_str, 1800)  # Cache for 30 minutes

    feed = feedparser.parse(feed_str)
    if filter is not None and filter != "":
        regex = re_compile(filter)
        feed.entries = [e for e in feed.entries if regex.search(getattr(e, "title"))]

    if feed_day_of_week_filter is not None and len(feed_day_of_week_filter) > 0:
        allowed_days = {_day_of_week_to_int(nd) for nd in normalized_days}

        def _is_allowed_day(entry: FeedParserDict) -> bool:
            try:
                pub_date_str = getattr(
                    entry, "published", getattr(entry, "pubDate", "")
                )
                pub_date: datetime = parser.parse(pub_date_str)
                return pub_date.weekday() in allowed_days
            except (ValueError, TypeError, AttributeError):
                # If pub_date is missing/invalid, exclude the episode
                return False

        feed.entries = [e for e in feed.entries if _is_allowed_day(e)]

    total = len(feed.entries)
    episodes = []
    for idx, entry in enumerate(feed.entries):
        episodes.append(parse_rss_entry(entry))
        if callback:
            callback(idx + 1, total)
    return episodes


def podcast_to_rss(channel: RssChannel, episodes: list[RssEpisode]) -> str:
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    channel_elem = ET.SubElement(rss, "channel")

    if channel.title:
        ET.SubElement(channel_elem, "title").text = channel.title
    if channel.author:
        ET.SubElement(channel_elem, "itunes:author").text = channel.author
    if channel.url:
        ET.SubElement(channel_elem, "url").text = channel.url
    if channel.description:
        ET.SubElement(channel_elem, "description").text = channel.description
    if channel.subtitle:
        ET.SubElement(channel_elem, "itunes:subtitle").text = channel.subtitle
    if channel.image:
        ET.SubElement(channel_elem, "itunes:image", href=channel.image)
        image_elem = ET.SubElement(channel_elem, "image")
        ET.SubElement(image_elem, "url").text = channel.image
        ET.SubElement(image_elem, "title").text = channel.title or ""
        ET.SubElement(image_elem, "url").text = channel.url or ""

    for episode in episodes:
        item = ET.SubElement(channel_elem, "item")
        if episode.id:
            ET.SubElement(item, "guid").text = episode.id
        if episode.title:
            ET.SubElement(item, "title").text = remove_control_chars(episode.title)
        if episode.description:
            ET.SubElement(item, "description").text = episode.description
        if episode.author:
            ET.SubElement(item, "itunes:author").text = episode.author
        if isinstance(episode.pub_date, datetime):
            ET.SubElement(item, "pubDate").text = episode.pub_date.isoformat()
        if episode.duration is not None:
            ET.SubElement(item, "itunes:duration").text = str(int(episode.duration))

        if episode.content:
            content_type, _ = mimetypes.guess_type(episode.content)
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", episode.content)
            enclosure.set("type", content_type or "audio/mpeg")

        if episode.image is not None and LINK_REGEX.match(episode.image):
            ET.SubElement(item, "itunes:image", href=episode.image)

    # Convert to string with pretty formatting
    rough_string = ET.tostring(rss, "utf-8")
    re_parsed = minidom.parseString(rough_string)
    return re_parsed.toprettyxml(indent="\t")


def rss_to_df(episodes: list[RssEpisode]) -> pd.DataFrame:
    """Convert RSS channel and episodes to a pandas DataFrame for analysis."""
    data = []
    for ep in episodes:
        data.append(
            {
                "id": ep.id,
                "title": ep.title,
                "author": ep.author,
                "description": f"{ep.description}".split("\n")[0][:64],
                "content": ep.content,
                "pub_date": ep.pub_date,
                "duration": ep.duration,
                "image": ep.image,
            }
        )
    df = pd.DataFrame(data)
    return df


def download_direct(url: str, dest: Path) -> tuple[Path, bool]:
    """Download from direct HTTP source."""
    # Use browser-like headers — some hosts block non-browser clients
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Encoding": "identity, deflate, br",
        "Connection": "keep-alive",
        "Referer": url,
    }

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
