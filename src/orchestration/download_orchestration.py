# Thin re-export shim for download orchestration helpers

from src.orchestration.download_service import (
    DownloadQueueItem,
    _apply_pairs,
    _audio_files,
    _build_channel,
    _download_queue_sort_key,
    _episode_sort_timestamp,
    _existing_media_sources,
    _ExistingMediaSources,
    _fill_channel,
    _match_to_s3,
    _prefixed_s3_key,
    _s3_prefix,
    _upload_rss,
    build_download_queue,
    episode_exists_on_s3,
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
