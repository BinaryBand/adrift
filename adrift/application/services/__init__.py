"""Application service helpers used by use-cases and CLI entrypoints.

These modules replace the legacy src.orchestration package as the primary
home for app-level coordination code.
"""

from .download_client import prefixed_s3_key, s3_prefix
from .download_enrich import enrich_with_sponsors
from .download_process import (
    DownloadQueueItem,
    build_download_queue,
    download_and_upload,
    episode_exists_on_s3,
    process_in_tmpdir,
)
from .download_rss import update_rss
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
    ManagedSecretField,
    describe_managed_secret,
)

__all__ = [
    "DownloadQueueItem",
    "MANAGED_S3_FIELDS",
    "ManagedSecretField",
    "MergeRunOptions",
    "MergeWriters",
    "build_download_queue",
    "describe_managed_secret",
    "download_and_upload",
    "emit_timings",
    "enrich_with_sponsors",
    "episode_exists_on_s3",
    "format_duration",
    "model_payloads",
    "prefixed_s3_key",
    "process_in_tmpdir",
    "s3_prefix",
    "series_output_paths",
    "update_rss",
    "write_json",
    "write_output_bundle",
    "write_report_file",
    "write_series_outputs",
]
