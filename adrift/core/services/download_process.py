"""Process helpers for the download pipeline."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from adrift.core.models import DownloadEpisode, MediaMetadata, PodcastConfig
from adrift.core.ports import Callback
from adrift.core.services.context import AppContext
from adrift.core.services.download_cache import _existing_media_sources
from adrift.core.services.download_client import storage_prefix
from adrift.core.services.download_upload import (
    _build_upload_request,
    _upload_episode_audio,
    _UploadRequest,
)
from adrift.core.services.events import (
    DownloadCompleted,
    DownloadFailed,
    OperationStarted,
    ProgressUpdated,
)
from adrift.core.services.files.audio import convert_to_opus, get_duration
from adrift.core.services.web.rss import download_direct
from adrift.core.services.web.sponsorblock import compute_ad_segments_expiry
from adrift.core.util.crypto import sha256_file
from adrift.core.util.title_normalization import normalize_title


@dataclass(frozen=True)
class DownloadQueueItem:
    """A queued episode plus whether it already exists in storage."""

    episode: DownloadEpisode
    exists_in_storage: bool


def _episode_slug(config: PodcastConfig, ep: DownloadEpisode) -> str:
    return normalize_title(config.name, ep.episode.title)


def episode_exists_in_storage(ep: DownloadEpisode, config: PodcastConfig, ctx: AppContext) -> bool:
    """Return True if ``ep`` is already uploaded for ``config``."""
    bucket, prefix = storage_prefix(config)
    cleaned_slug = _episode_slug(config, ep)
    key_prefix = f"{prefix}/{cleaned_slug}"
    if ctx.storage.exists(bucket, key_prefix) is not None:
        return True
    return _existing_media_sources(ctx, bucket, prefix, config.name).matches(ep, cleaned_slug)


def build_download_queue(
    episodes: list[DownloadEpisode], config: PodcastConfig, ctx: AppContext
) -> list[DownloadQueueItem]:
    """Build the queue of episodes, flagging those already in storage."""
    queue = [
        DownloadQueueItem(
            episode=episode,
            exists_in_storage=episode_exists_in_storage(episode, config, ctx),
        )
        for episode in episodes
    ]
    return sorted(queue, key=_download_queue_sort_key)


def _download_queue_sort_key(item: DownloadQueueItem) -> tuple[bool, float, str]:
    episode = item.episode.episode
    return (
        item.exists_in_storage,
        -_episode_sort_timestamp(episode.pub_date),
        episode.title,
    )


def _episode_sort_timestamp(pub_date: datetime | None) -> float:
    if pub_date is None:
        return datetime.min.replace(tzinfo=UTC).timestamp()
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=UTC)
    return pub_date.timestamp()


def download_and_upload(
    ep: DownloadEpisode,
    config: PodcastConfig,
    ctx: AppContext,
) -> bool:
    """Download one episode, remove ads, convert to Opus, upload to storage.

    Returns True if newly uploaded, False if already present in storage.
    """
    bucket, prefix = storage_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    if ctx.storage.exists(bucket, key_prefix):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        return process_in_tmpdir(ep, config, Path(tmp), ctx)


def process_in_tmpdir(
    ep: DownloadEpisode,
    config: PodcastConfig,
    tmp: Path,
    ctx: AppContext,
) -> bool:
    """Download, convert, and upload ``ep`` using ``tmp`` as scratch space."""
    bucket, prefix = storage_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    audio = _download_episode_audio(ep, tmp, ctx)
    if audio is None:
        _publish_download_failed(ctx, ep)
        return False
    opus = _prepare_upload_audio(ep, audio, ctx)
    duration = get_duration(opus)
    metadata = _build_metadata(ep, opus, duration)
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
            storage_key=upload_request.key,
            ad_segments_found=bool(ep.sponsor_segments),
        )
    )
    return True


def _progress_callback(ctx: AppContext) -> Callback:
    def callback(current: int, total: int | None) -> None:
        ctx.event_bus.publish(ProgressUpdated(current=current, total=total))

    return callback


def _download_audio(ep: DownloadEpisode, dest: Path, ctx: AppContext) -> Path | None:
    callback = _progress_callback(ctx)
    if ep.video_id:
        if ctx.video_downloader is None:
            msg = "AppContext.video_downloader must be set to download video sources"
            raise RuntimeError(msg)
        return ctx.video_downloader.download(ep.episode.content, dest, callback=callback)
    return download_direct(ep.episode.content, dest)


def _download_episode_audio(ep: DownloadEpisode, tmp: Path, ctx: AppContext) -> Path | None:
    ctx.event_bus.publish(OperationStarted(label=f"download audio: {ep.episode.title}"))
    return _download_audio(ep, tmp, ctx)


def _prepare_upload_audio(ep: DownloadEpisode, audio: Path, ctx: AppContext) -> Path:
    ctx.event_bus.publish(OperationStarted(label=f"convert opus: {ep.episode.title}"))
    return convert_to_opus(audio, callback=_progress_callback(ctx))


def _build_metadata(ep: DownloadEpisode, opus: Path, duration: float | None) -> MediaMetadata:
    pub_date = ep.episode.pub_date or datetime.now(tz=UTC)
    now = datetime.now(tz=UTC)
    video_age_days = (now - pub_date.replace(tzinfo=pub_date.tzinfo or UTC)).days
    return MediaMetadata(
        duration=duration or 0.0,
        source=ep.episode.content,
        upload_date=pub_date,
        audio_hash=sha256_file(opus),
        ad_segments=ep.sponsor_segments,
        ad_segments_expires_at=(
            compute_ad_segments_expiry(video_age_days, now) if ep.sponsor_segments else None
        ),
    )


__all__ = [
    "DownloadQueueItem",
    "build_download_queue",
    "download_and_upload",
    "episode_exists_in_storage",
    "process_in_tmpdir",
]
