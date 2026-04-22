"""Cached helpers for download orchestration (existing media sources)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.files.s3 import get_file_list, get_metadata
from src.orchestration.download_client import _prefixed_s3_key
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.utils.title_normalization import normalize_title


@dataclass(frozen=True)
class _ExistingMediaSources:
    cleaned_slugs: frozenset[str]
    source_urls: frozenset[str]
    youtube_video_ids: frozenset[str]

    def matches(self, ep: object, cleaned_slug: str) -> bool:
        if cleaned_slug in self.cleaned_slugs:
            return True
        content = getattr(ep, "episode", None)
        if content and getattr(content, "content", None) in self.source_urls:
            return True
        video_id = getattr(ep, "video_id", None)
        return video_id is not None and video_id in self.youtube_video_ids


@lru_cache(maxsize=128)
def _existing_media_sources(bucket: str, prefix: str, show: str) -> _ExistingMediaSources:
    cleaned_slugs: set[str] = set()
    source_urls: set[str] = set()
    youtube_video_ids: set[str] = set()

    for name in get_file_list(bucket, prefix, False):
        cleaned_slugs.add(normalize_title(show, Path(name).stem))
        metadata = get_metadata(bucket, _prefixed_s3_key(prefix, name))
        if metadata is None:
            continue
        source = getattr(metadata, "source", None)
        if source:
            source_urls.add(source)
            m = YOUTUBE_VIDEO_REGEX.search(source)
            if m:
                youtube_video_ids.add(m.group(4))

    return _ExistingMediaSources(
        frozenset(cleaned_slugs),
        frozenset(source_urls),
        frozenset(youtube_video_ids),
    )


__all__ = ["_existing_media_sources", "_ExistingMediaSources"]
