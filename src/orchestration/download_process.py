"""Process and orchestration helpers for download pipeline."""

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.files.audio import convert_to_opus, cut_segments, get_duration
from src.files.s3 import exists
from src.models import DownloadEpisode, MediaMetadata, PodcastConfig
from src.orchestration.download_cache import _existing_media_sources
from src.orchestration.download_upload import _build_upload_request, _upload_episode_audio
from src.utils.progress import Callback
from src.utils.title_normalization import normalize_title
from src.web.rss import download_direct
from src.youtube.downloader import download_video


@dataclass(frozen=True)
class DownloadQueueItem:
    episode: DownloadEpisode
    exists_on_s3: bool


@dataclass(frozen=True)
class DownloadProgressHooks:
    on_operation: Callable[[str], None] | None = None
    on_progress: Callback | None = None
    on_complete: Callable[[], None] | None = None


def _start_operation(hooks: DownloadProgressHooks | None, label: str) -> None:
    if hooks is not None and hooks.on_operation is not None:
        hooks.on_operation(label)


def _complete_operation(hooks: DownloadProgressHooks | None) -> None:
    if hooks is not None and hooks.on_complete is not None:
        hooks.on_complete()


def _operation_progress(hooks: DownloadProgressHooks | None) -> Callback | None:
    if hooks is None:
        return None
    return hooks.on_progress


def _episode_slug(config: PodcastConfig, ep: DownloadEpisode) -> str:
    return normalize_title(config.name, ep.episode.title)


def episode_exists_on_s3(ep: DownloadEpisode, config: PodcastConfig) -> bool:
    from src.orchestration import download_service as _download_service

    bucket, prefix = _download_service._s3_prefix(config)
    cleaned_slug = _episode_slug(config, ep)
    key_prefix = f"{prefix}/{cleaned_slug}"
    if exists(bucket, key_prefix) is not None:
        return True
    return _existing_media_sources(bucket, prefix, config.name).matches(ep, cleaned_slug)


def build_download_queue(
    episodes: list[DownloadEpisode], config: PodcastConfig
) -> list[DownloadQueueItem]:
    queue = [
        DownloadQueueItem(episode=episode, exists_on_s3=episode_exists_on_s3(episode, config))
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
    progress_hooks: DownloadProgressHooks | None = None,
) -> bool:
    """Download one episode, remove ads, convert to Opus, upload to S3.

    Returns True if newly uploaded, False if already present on S3.
    """
    from src.orchestration import download_service as _download_service

    bucket, prefix = _download_service._s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    if exists(bucket, key_prefix):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        return process_in_tmpdir(ep, config, Path(tmp), progress_hooks)


def process_in_tmpdir(
    ep: DownloadEpisode,
    config: PodcastConfig,
    tmp: Path,
    progress_hooks: DownloadProgressHooks | None,
) -> bool:
    from src.orchestration import download_service as _download_service

    bucket, prefix = _download_service._s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    audio = _download_episode_audio(ep, tmp, progress_hooks)
    if audio is None:
        _complete_operation(progress_hooks)
        return False
    opus = _prepare_upload_audio(ep, audio, progress_hooks)
    duration = get_duration(opus)
    metadata = _build_metadata(ep, duration, sponsors_removed=bool(ep.sponsor_segments))
    upload_request = _build_upload_request(bucket, key_prefix, opus, metadata)
    _upload_episode_audio(ep, upload_request, progress_hooks)
    _complete_operation(progress_hooks)
    return True


def _download_audio(
    ep: DownloadEpisode, dest: Path, callback: Callback | None = None
) -> Path | None:
    if ep.video_id:
        return download_video(ep.episode.content, dest, callback=callback)
    return download_direct(ep.episode.content, dest)


def _download_episode_audio(
    ep: DownloadEpisode, tmp: Path, progress_hooks: DownloadProgressHooks | None
) -> Path | None:
    _start_operation(progress_hooks, f"download audio: {ep.episode.title}")
    return _download_audio(ep, tmp, _operation_progress(progress_hooks))


def _prepare_upload_audio(
    ep: DownloadEpisode, audio: Path, progress_hooks: DownloadProgressHooks | None
) -> Path:
    if ep.sponsor_segments:
        _start_operation(progress_hooks, f"cut sponsors: {ep.episode.title}")
        cut_segments(audio, ep.sponsor_segments, callback=_operation_progress(progress_hooks))
    _start_operation(progress_hooks, f"convert opus: {ep.episode.title}")
    return convert_to_opus(audio, callback=_operation_progress(progress_hooks))


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
    "DownloadQueueItem",
    "DownloadProgressHooks",
    "build_download_queue",
    "episode_exists_on_s3",
    "download_and_upload",
    "process_in_tmpdir",
]
