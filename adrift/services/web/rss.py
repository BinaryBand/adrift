import mimetypes
import shutil
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.dom import minidom

import requests

from adrift.models import RssChannel, RssEpisode
from adrift.utils.regex import LINK_REGEX, re_compile

_CONTROL_CHARS_RE = re_compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def podcast_to_rss(channel: RssChannel, episodes: list[RssEpisode]) -> str:
    """Serialize a podcast channel and its episodes to an RSS XML string."""
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
    return _CONTROL_CHARS_RE.sub("", episode.title)


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


def download_direct(url: str, dest: Path) -> Path:
    """Download audio from a direct HTTP URL into dest directory."""
    headers = _browser_headers_for(url)
    with requests.get(url, stream=True, headers=headers, timeout=60) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(content_type) or ".mp3"
        dest.mkdir(parents=True, exist_ok=True)
        staging_file = dest / f"{uuid.uuid4().hex}{ext}"
        response.raw.decode_content = True
        with open(staging_file, "wb") as f:
            shutil.copyfileobj(response.raw, f)
    return staging_file


def _browser_headers_for(url: str) -> dict[str, str]:
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
