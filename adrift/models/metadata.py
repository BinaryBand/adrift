import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable

import pydantic
from pydantic import BaseModel, ConfigDict, field_validator

DEVICE = os.getenv("DEVICE", "UnknownDevice")
PROJECT = os.getenv("PROJECT", "UnknownProject")


class S3Metadata(pydantic.BaseModel, ABC):
    """Abstract base class for S3 metadata models."""

    uploader: str | None = pydantic.Field(default=DEVICE, description="Device identifier")

    @abstractmethod
    def to_dict(self) -> dict[str, str]: ...


class CacheMetadata(S3Metadata):
    """S3 object metadata for cached items."""

    created_at: datetime = pydantic.Field(description="Creation timestamp")
    expires_at: datetime | None = pydantic.Field(default=None, description="Expiration timestamp")

    def to_dict(self) -> dict[str, str]:
        result: dict[str, str] = {"created_at": self.created_at.isoformat()}
        if self.expires_at is not None:
            result["expires_at"] = self.expires_at.isoformat()
        if self.uploader is not None:
            result["uploader"] = self.uploader
        return result


class MediaMetadata(S3Metadata):
    """S3 object metadata for media files."""

    duration: float = pydantic.Field(description="Duration in seconds")
    source: str = pydantic.Field(description="Source URL of the media")
    upload_date: datetime = pydantic.Field(description="Date the media was uploaded")
    audio_hash: str | None = pydantic.Field(
        default=None, description="SHA-256 hash of the uploaded audio file bytes"
    )
    ad_segments: list[tuple[float, float]] = pydantic.Field(
        default_factory=list, description="Known ad segments as (start, end) second offsets"
    )
    ad_segments_expires_at: datetime | None = pydantic.Field(
        default=None, description="When ad_segments should be considered stale"
    )

    @field_validator("ad_segments", mode="before")
    @classmethod
    def _parse_ad_segments(cls, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value) if value else []
        return value

    def to_dict(self) -> dict[str, str]:
        result = {
            "duration": str(self.duration),
            "source": self.source,
            "upload_date": self.upload_date.isoformat(),
            "ad_segments": json.dumps(self.ad_segments),
            "uploader": self.uploader if self.uploader is not None else "unknown",
        }
        if self.audio_hash is not None:
            result["audio_hash"] = self.audio_hash
        if self.ad_segments_expires_at is not None:
            result["ad_segments_expires_at"] = self.ad_segments_expires_at.isoformat()
        return result


class YtDlpParams(BaseModel):
    """Typed yt-dlp options as a Pydantic model.

    All fields are optional (None means yt-dlp uses its own default).  Use
    attribute access to read and write: ``opts.format = "bestaudio"``.
    """

    quiet: bool | None = None
    no_warnings: bool | None = None
    logger: Any | None = None
    extract_flat: bool | None = None
    socket_timeout: int | None = None
    sleep_interval: int | None = None
    max_sleep_interval: int | None = None
    sleep_interval_requests: int | None = None
    cookiefile: str | None = None
    cookiesfrombrowser: tuple[str, ...] | None = None
    format: str | None = None
    outtmpl: str | None = None
    postprocessors: list[dict[str, Any]] | None = None
    progress_hooks: list[Callable[[dict[str, Any]], None]] | None = None
    playlistreverse: bool | None = None
    playliststart: int | None = None
    playlistend: int | None = None
    extractor_args: Any | None = None
    remote_components: Any | None = None
    ratelimit: int | None = None
    js_runtimes: dict[str, dict[str, Any]] | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class RssChannel(BaseModel):
    title: str
    author: str
    subtitle: str
    url: str
    description: str
    image: str


class RssEpisode(BaseModel):
    id: str
    title: str
    author: str
    content: str
    description: str | None = None
    duration: float | None = None
    pub_date: datetime | None = None
    image: str | None = None

    # Internal field to track availability (not exposed in RSS)
    _availability: str | None = None

    @property
    def is_public(self) -> bool:
        """Check if video is publicly available."""
        return self._availability in (None, "public")
