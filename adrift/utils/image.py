"""Image URL extraction utilities for feedparser and yt-dlp data shapes."""

from typing import Any


def _str_from_mapping(obj: object, *keys: str) -> str:
    get = getattr(obj, "get", None)
    if not callable(get):
        return ""
    for key in keys:
        val = get(key, None)
        if isinstance(val, str) and val:
            return val
    return ""


def _str_from_attrs(obj: object, *keys: str) -> str:
    for key in keys:
        val = getattr(obj, key, None)
        if isinstance(val, str) and val:
            return val
    return ""


def extract_image_from_feedparser(obj: object) -> str:
    """Extract an image URL from a feedparser channel field.

    feedparser returns image data as strings, dicts with 'href'/'url' keys,
    or objects with the same attributes — this handles all three forms.
    """
    if isinstance(obj, str):
        return obj
    return _str_from_mapping(obj, "href", "url") or _str_from_attrs(obj, "href", "url")


def extract_image_from_ytdlp(value: Any) -> str:
    """Extract an image URL from a YtDlpImage model or raw dict."""
    if isinstance(value, dict):
        url_value = value.get("url")
        return url_value if isinstance(url_value, str) else ""
    url = getattr(value, "url", None)
    return url if isinstance(url, str) else ""


def extract_image_from_ytdlp_list(data: list[Any]) -> str:
    """Extract an image URL from the last entry in a yt-dlp thumbnail list."""
    if not data:
        return ""
    return extract_image_from_ytdlp(data[-1])
