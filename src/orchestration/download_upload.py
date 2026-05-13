"""Compatibility shim for legacy upload imports."""

from src.application.services.download_upload import (
    _build_upload_request,
    _upload_episode_audio,
    _UploadRequest,
)

__all__ = ["_UploadRequest", "_build_upload_request", "_upload_episode_audio"]
