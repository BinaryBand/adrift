"""Process helpers for the download pipeline."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from adrift.adapters.process.youtube.downloader import BotDetectionError, download_video
from adrift.models import DownloadEpisode, MediaMetadata, PodcastConfig
from adrift.services.download_cache import _existing_media_sources
from adrift.services.download_client import s3_prefix
from adrift.services.download_upload import (
    _build_upload_request,
    _upload_episode_audio,
    _UploadRequest,
)
from adrift.services.events import (
    DownloadCompleted,
    DownloadFailed,
    OperationStarted,
    ProgressUpdated,
)
from adrift.services.files.audio import convert_to_opus, cut_segments, get_duration
from adrift.services.web.rss import download_direct
from adrift.utils.title_normalization import normalize_title

if TYPE_CHECKING:
    from adrift.services.context import AppContext


@dataclass(frozen=True)
class DownloadQueueItem:
    episode: DownloadEpisode
    exists_on_s3: bool


def _episode_slug(config: PodcastConfig, ep: DownloadEpisode) -> str:
    return normalize_title(config.name, ep.episode.title)


def _s3_service(ctx: AppContext) -> Any:
    return cast(Any, ctx.s3)


def episode_exists_on_s3(ep: DownloadEpisode, config: PodcastConfig, ctx: AppContext) -> bool:
    bucket, prefix = s3_prefix(config)
    cleaned_slug = _episode_slug(config, ep)
    key_prefix = f"{prefix}/{cleaned_slug}"
    if _s3_service(ctx).exists(bucket, key_prefix) is not None:
        return True
    return _existing_media_sources(ctx, bucket, prefix, config.name).matches(ep, cleaned_slug)


def build_download_queue(
    episodes: list[DownloadEpisode], config: PodcastConfig, ctx: AppContext
) -> list[DownloadQueueItem]:
    queue = [
        DownloadQueueItem(
            episode=episode,
            exists_on_s3=episode_exists_on_s3(episode, config, ctx),
        )
        for episode in episodes
    ]
    return sorted(queue, key=_download_queue_sort_key)


def _download_queue_sort_key(item: DownloadQueueItem) -> tuple[bool, float, str]:
    episode = item.episode.episode
    return (
        item.exists_on_s3,
        -_episode_sort_timestamp(episode.pub_date),
        episode.title,
    )


def _episode_sort_timestamp(pub_date: datetime | None) -> float:
    if pub_date is None:
        return datetime.min.replace(tzinfo=timezone.utc).timestamp()
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    return pub_date.timestamp()


def download_and_upload(
    ep: DownloadEpisode,
    config: PodcastConfig,
    ctx: AppContext,
) -> bool:
    """Download one episode, remove ads, convert to Opus, upload to S3.

    Returns True if newly uploaded, False if already present on S3.
    """
    bucket, prefix = s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    if _s3_service(ctx).exists(bucket, key_prefix):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        return process_in_tmpdir(ep, config, Path(tmp), ctx)


def process_in_tmpdir(
    ep: DownloadEpisode,
    config: PodcastConfig,
    tmp: Path,
    ctx: AppContext,
) -> bool:
    bucket, prefix = s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    audio = _download_episode_audio(ep, tmp, ctx)
    if audio is None:
        _publish_download_failed(ctx, ep)
        return False
    opus = _prepare_upload_audio(ep, audio, ctx)
    duration = get_duration(opus)
    metadata = _build_metadata(ep, duration, sponsors_removed=bool(ep.sponsor_segments))
    upload_request = _build_upload_request(bucket, key_prefix, opus, metadata)
    return _upload_and_publish_completion(ep, upload_request, ctx)


def _publish_download_failed(ctx: AppContext, ep: DownloadEpisode) -> None:
    ctx.event_bus.publish(
        DownloadFailed(
            episode=ep.episode,
            error="Audio download failed",
            recoverable=True,
        )
    )


def _upload_and_publish_completion(
    ep: DownloadEpisode,
    upload_request: _UploadRequest,
    ctx: AppContext,
) -> bool:
    ctx.event_bus.publish(OperationStarted(label=f"upload opus: {ep.episode.title}"))
    _upload_episode_audio(upload_request, ctx, callback=_progress_callback(ctx))
    ctx.event_bus.publish(
        DownloadCompleted(
            episode=ep.episode,
            s3_key=upload_request.key,
            sponsors_removed=bool(ep.sponsor_segments),
        )
    )
    return True


def _progress_callback(ctx: AppContext):
    def callback(current: int, total: int | None) -> None:
        ctx.event_bus.publish(ProgressUpdated(current=current, total=total))

    return callback


def _download_audio(ep: DownloadEpisode, dest: Path, ctx: AppContext) -> Path | None:
    callback = _progress_callback(ctx)
    if ep.video_id:
        return download_video(ep.episode.content, dest, callback=callback)
    return download_direct(ep.episode.content, dest)


def _download_episode_audio(ep: DownloadEpisode, tmp: Path, ctx: AppContext) -> Path | None:
    ctx.event_bus.publish(OperationStarted(label=f"download audio: {ep.episode.title}"))
    return _download_audio(ep, tmp, ctx)


def _prepare_upload_audio(ep: DownloadEpisode, audio: Path, ctx: AppContext) -> Path:
    if ep.sponsor_segments:
        ctx.event_bus.publish(OperationStarted(label=f"cut sponsors: {ep.episode.title}"))
        cut_segments(
            audio,
            ep.sponsor_segments,
            callback=_progress_callback(ctx),
        )
    ctx.event_bus.publish(OperationStarted(label=f"convert opus: {ep.episode.title}"))
    return convert_to_opus(audio, callback=_progress_callback(ctx))


def _build_metadata(
    ep: DownloadEpisode, duration: float | None, *, sponsors_removed: bool
) -> MediaMetadata:
    pub_date = ep.episode.pub_date or datetime.now(tz=timezone.utc)
    return MediaMetadata(
        duration=duration or 0.0,
        source=ep.episode.content,
        upload_date=pub_date,
        sponsors_removed=sponsors_removed,
    )


__all__ = [
    "BotDetectionError",
    "DownloadQueueItem",
    "build_download_queue",
    "episode_exists_on_s3",
    "download_and_upload",
    "process_in_tmpdir",
]
