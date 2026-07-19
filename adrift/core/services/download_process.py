"""Process helpers for the download pipeline."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from adrift.core.ports import Callback as PortCallback
from adrift.core.models import DownloadEpisode, MediaMetadata, PodcastConfig
from adrift.core.services.download_cache import _existing_media_sources
from adrift.core.services.download_client import storage_prefix
from adrift.core.services.download_upload import (
    _build_upload_request,
    _upload_episode_audio,
    _UploadRequest,
)
from adrift.core.services.events import (
    DownloadCompleted,
    DownloadFailed,
    OperationStarted,
    ProgressUpdated,
)
from adrift.core.services.files.audio import convert_to_opus, get_duration
from adrift.core.services.web.rss import download_direct
from adrift.core.services.web.sponsorblock import compute_ad_segments_expiry
from adrift.core.util.crypto import sha256_file
from adrift.core.util.title_normalization import normalize_title

if TYPE_CHECKING:
    from adrift.core.services.context import AppContext


@dataclass(frozen=True)
class DownloadQueueItem:
    """A queued episode plus whether it already exists in storage."""
