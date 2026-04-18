# cspell: words youtu

import re

from cachetools import LRUCache, cached

_RE_COMPILE_CACHE: LRUCache[str, re.Pattern[str]] = LRUCache(2048)


@cached(_RE_COMPILE_CACHE)
def re_compile(regex: str) -> re.Pattern[str]:
    return re.compile(regex)


# yt://@channel_name
# yt://#playlist_id
# s3://bucket_name/path/to/object


LINK_REGEX = re_compile(r"https?://\S+")

YOUTUBE_VIDEO_REGEX = re_compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/watch\?v=([\w-]+)"
)

YT_CHANNEL = re_compile(r"^https?://(www\.)?youtube\.com/@([A-Za-z0-9_\-]+)(/videos)?$")

YT_CHANNEL_SHORTHAND = re_compile(r"^yt://@([A-Za-z0-9_\-]+)$")
YOUTUBE_PLAYLIST_SHORTHAND_REGEX = re_compile(r"^yt://#([A-Za-z0-9_\-]+)$")
