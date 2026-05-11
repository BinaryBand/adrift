"""Application service helpers used by use-cases and runbooks.

These modules replace the legacy src.orchestration package as the primary
home for app-level coordination code.
"""

from .download_cache import _existing_media_sources, _ExistingMediaSources
from .download_client import prefixed_s3_key, s3_prefix
from .download_enrich import _extract_video_id, enrich_with_sponsors
from .download_process import (
    DownloadQueueItem,
    build_download_queue,
    download_and_upload,
    episode_exists_on_s3,
    process_in_tmpdir,
)
from .download_rss import update_rss
from .download_upload import _build_upload_request, _upload_episode_audio, _UploadRequest
from .merge_service import (
    MergeRunOptions,
    MergeWriters,
    emit_timings,
    format_duration,
    model_payloads,
    series_output_paths,
    write_json,
    write_output_bundle,
    write_report_file,
    write_series_outputs,
)
from .secret_service import (
    MANAGED_S3_FIELDS,
    MANAGED_S3_KEYS,
    ManagedSecretField,
    ManagedSecretState,
    collect_secret_states,
    delete_secret_value,
    describe_managed_secret,
    is_writable_secret_store,
    set_secret_value,
    validate_required_secret_values,
    validate_s3_connection,
)

__all__ = [
    "DownloadQueueItem",
    "MANAGED_S3_FIELDS",
    "MANAGED_S3_KEYS",
    "ManagedSecretField",
    "ManagedSecretState",
    "MergeRunOptions",
    "MergeWriters",
    "_ExistingMediaSources",
    "_UploadRequest",
    "_build_upload_request",
    "_existing_media_sources",
    "_extract_video_id",
    "_upload_episode_audio",
    "build_download_queue",
    "collect_secret_states",
    "delete_secret_value",
    "describe_managed_secret",
    "download_and_upload",
    "emit_timings",
    "enrich_with_sponsors",
    "episode_exists_on_s3",
    "format_duration",
    "is_writable_secret_store",
    "model_payloads",
    "prefixed_s3_key",
    "process_in_tmpdir",
    "s3_prefix",
    "series_output_paths",
    "set_secret_value",
    "update_rss",
    "validate_required_secret_values",
    "validate_s3_connection",
    "write_json",
    "write_output_bundle",
    "write_report_file",
    "write_series_outputs",
]
