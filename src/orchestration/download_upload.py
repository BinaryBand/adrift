"""Upload helpers for the download pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.files.s3 import UploadOptions, upload_file
from src.models import DownloadEpisode, MediaMetadata


@dataclass(frozen=True)
class _UploadRequest:
    bucket: str
    key: str
    opus: Path
    metadata: MediaMetadata


def _build_upload_request(
    bucket: str, key_prefix: str, opus: Path, metadata: MediaMetadata
) -> _UploadRequest:
    return _UploadRequest(bucket=bucket, key=f"{key_prefix}.opus", opus=opus, metadata=metadata)


def _upload_episode_audio(ep: DownloadEpisode, request: _UploadRequest, hooks: Any) -> None:
    """Upload an opus file, using `hooks` for progress notifications."""
    hooks.on_operation(f"upload opus: {ep.episode.title}")
    upload_file(
        request.bucket,
        request.key,
        request.opus,
        UploadOptions(metadata=request.metadata, callback=hooks.on_progress),
    )


__all__ = ["_UploadRequest", "_build_upload_request", "_upload_episode_audio"]
