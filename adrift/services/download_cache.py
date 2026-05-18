"""Cached helpers for download services (existing media sources)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from adrift.models import MediaMetadata
from adrift.services.download_client import prefixed_s3_key
from adrift.utils.regex import YOUTUBE_VIDEO_REGEX
from adrift.utils.title_normalization import normalize_title

if TYPE_CHECKING:
    from adrift.services.context import AppContext


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


def _s3_service(ctx: AppContext) -> Any:
    return cast(Any, ctx.s3)


def _existing_media_sources(
    ctx: AppContext, bucket: str, prefix: str, show: str
) -> _ExistingMediaSources:
    cleaned_slugs: set[str] = set()
    source_urls: set[str] = set()
    youtube_video_ids: set[str] = set()

    s3 = _s3_service(ctx)
    for name in s3.get_file_list(bucket, prefix, False):
        cleaned_slugs.add(normalize_title(show, Path(name).stem))
        metadata = cast(
            MediaMetadata | None,
            s3.get_metadata(bucket, prefixed_s3_key(prefix, name)),
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
