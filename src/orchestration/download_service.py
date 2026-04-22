"""Thin re-export shim for the download orchestration modules.

This module preserves the original public import surface while the
implementation is split into smaller files under src.orchestration.
"""

from src.orchestration.download_cache import _existing_media_sources, _ExistingMediaSources
from src.orchestration.download_client import _prefixed_s3_key, _s3_prefix
from src.orchestration.download_enrich import _extract_video_id, enrich_with_sponsors
from src.orchestration.download_process import (
    DownloadProgressHooks,
    DownloadQueueItem,
    build_download_queue,
    download_and_upload,
    episode_exists_on_s3,
    process_in_tmpdir,
)
from src.orchestration.download_rss import update_rss
from src.orchestration.download_upload import (
    _build_upload_request,
    _upload_episode_audio,
    _UploadRequest,
)

__all__ = [
    "enrich_with_sponsors",
    "_extract_video_id",
    "_s3_prefix",
    "_prefixed_s3_key",
    "_existing_media_sources",
    "_ExistingMediaSources",
    "DownloadQueueItem",
    "DownloadProgressHooks",
    "build_download_queue",
    "episode_exists_on_s3",
    "download_and_upload",
    "process_in_tmpdir",
    "_UploadRequest",
    "_build_upload_request",
    "_upload_episode_audio",
    "update_rss",
]
