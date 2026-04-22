"""Thin re-export shim for download orchestration helpers."""

from src.orchestration.download_cache import _existing_media_sources, _ExistingMediaSources
from src.orchestration.download_client import _prefixed_s3_key, _s3_prefix
from src.orchestration.download_process import (
    DownloadQueueItem,
    _download_queue_sort_key,
    _episode_sort_timestamp,
    build_download_queue,
    episode_exists_on_s3,
)
from src.orchestration.download_rss import (
    _apply_pairs,
    _audio_files,
    _build_channel,
    _fill_channel,
    _match_to_s3,
    _upload_rss,
    update_rss,
)

__all__ = [
    "DownloadQueueItem",
    "build_download_queue",
    "episode_exists_on_s3",
    "_ExistingMediaSources",
    "_existing_media_sources",
    "_prefixed_s3_key",
    "_download_queue_sort_key",
    "_episode_sort_timestamp",
    "update_rss",
    "_build_channel",
    "_fill_channel",
    "_match_to_s3",
    "_audio_files",
    "_apply_pairs",
    "_upload_rss",
    "_s3_prefix",
]
