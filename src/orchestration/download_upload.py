"""Upload helpers for the download pipeline."""

from dataclasses import dataclass
from pathlib import Path

from src.files.s3 import UploadOptions, upload_file
from src.models import MediaMetadata
from src.utils.progress import Callback


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


def _upload_episode_audio(request: _UploadRequest, callback: Callback | None = None) -> None:
    """Upload an opus file with an optional progress callback."""
    upload_file(
        request.bucket,
        request.key,
        request.opus,
        UploadOptions(metadata=request.metadata, callback=callback),
    )


__all__ = ["_UploadRequest", "_build_upload_request", "_upload_episode_audio"]
