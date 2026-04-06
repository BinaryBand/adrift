import re

from cachetools import LRUCache, cached


@cached(LRUCache(2048))
def re_compile(regex: str) -> re.Pattern[str]:
    return re.compile(regex)


# yt://@channel_name
# yt://#playlist_id
# s3://bucket_name/path/to/object


LINK_REGEX = re_compile(r"https?://\S+")

YT_CHANNEL = re_compile(r"^https?://(www\.)?youtube\.com/@([A-Za-z0-9_\-]+)(/videos)?$")

YOUTUBE_PLAYLIST_REGEX = re_compile(
    r"^https?://(www\.)?youtube\.com/playlist\?list=([A-Za-z0-9_\-]+)$"
)

YT_CHANNEL_SHORTHAND = re_compile(r"^yt://@([A-Za-z0-9_\-]+)$")
YOUTUBE_PLAYLIST_SHORTHAND_REGEX = re_compile(r"^yt://#([A-Za-z0-9_\-]+)$")

YOUTUBE_VIDEO_REGEX = re_compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/watch\?v=([\w-]+)")

SEGMENT_TIME_REGEX = re_compile(r"(\d+\.\d+)_(\d+\.\d+)\b")
