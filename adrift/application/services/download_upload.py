"""Upload helpers for application download services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from adrift.files.s3 import UploadOptions
from adrift.models import MediaMetadata
from adrift.utils.progress import Callback

if TYPE_CHECKING:
    from adrift.application.context import AppContext


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


def _s3_service(ctx: AppContext) -> Any:
    return cast(Any, ctx.s3)


def _upload_episode_audio(
    request: _UploadRequest,
    ctx: AppContext,
    callback: Callback | None = None,
) -> None:
    """Upload an opus file with an optional progress callback."""
    _s3_service(ctx).upload_file(
        (request.bucket, request.key),
        request.opus,
        UploadOptions(metadata=request.metadata, callback=callback),
    )


__all__ = ["_UploadRequest", "_build_upload_request", "_upload_episode_audio"]
