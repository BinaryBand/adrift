"""Cached helpers for download services (existing media sources)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from adrift.core.models import MediaMetadata
from adrift.core.services.download_client import prefixed_key
from adrift.core.util.regex import YOUTUBE_VIDEO_REGEX
from adrift.core.util.title_normalization import normalize_title

if TYPE_CHECKING:
    from adrift.core.services.context import AppContext


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


def _existing_media_sources(
    ctx: AppContext, bucket: str, prefix: str, show: str
) -> _ExistingMediaSources:
    cleaned_slugs: set[str] = set()
    source_urls: set[str] = set()
    youtube_video_ids: set[str] = set()

    for name in ctx.storage.get_file_list(bucket, prefix, False):
        cleaned_slugs.add(normalize_title(show, Path(name).stem))
        metadata: MediaMetadata | None = ctx.storage.get_metadata(
            bucket, prefixed_key(prefix, name)
        )
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
