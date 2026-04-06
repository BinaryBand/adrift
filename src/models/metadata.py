import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypedDict

import pydantic
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel

# Ensure project root is on sys.path when executed as script
sys.path.insert(0, Path(__file__).parent.parent.as_posix())
load_dotenv(find_dotenv())
DEVICE = os.getenv("DEVICE", "UnknownDevice")
PROJECT = os.getenv("PROJECT", "UnknownProject")


class S3Metadata(pydantic.BaseModel, ABC):
    """Abstract base class for S3 metadata models."""

    uploader: str | None = pydantic.Field(
        default=DEVICE, description="Device identifier"
    )

    @abstractmethod
    def to_dict(self) -> dict[str, str]:
        """Convert to S3-compatible metadata dictionary (all string values)."""
        pass


class CacheMetadata(S3Metadata):
    """S3 object metadata for cached items."""

    created_at: datetime = pydantic.Field(description="Creation timestamp")
    expires_at: datetime | None = pydantic.Field(
        default=None, description="Expiration timestamp"
    )

    def to_dict(self) -> dict[str, str]:
        """Convert to S3-compatible metadata dictionary (all string values)."""
        result: dict[str, str] = {
            "created_at": self.created_at.isoformat(),
        }
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
    sponsors_removed: bool | None = pydantic.Field(
        default=False, description="Whether ads were removed"
    )

    def to_dict(self) -> dict[str, str]:
        """Convert to S3-compatible metadata dictionary (all string values)."""
        return {
            "duration": str(self.duration),
            "source": self.source,
            "upload_date": self.upload_date.isoformat(),
            "sponsors_removed": "true" if self.sponsors_removed else "false",
            "uploader": self.uploader if self.uploader is not None else "unknown",
        }


class YtDlpParams(BaseModel):
    """Typed yt-dlp options as a Pydantic model.

    This model is intentionally permissive (extra fields allowed) and
    implements mapping-style access so it can be used interchangeably with
    plain dicts in existing call sites (e.g., `opts["format"] = "..."`).
    """

    quiet: bool | None = None
    no_warnings: bool | None = None
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

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key) if hasattr(self, key) else self.model_dump().get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            setattr(self, key, value)
        except Exception:
            # Fallback to storing in the extra dict
            data = self.model_dump()
            data[key] = value
            self.model_validate(data)


def _extract_image_from_list(data: list[Any]) -> str:
    last = data[-1] if data else None
    return last.get("url", "") if isinstance(last, dict) else ""


class RssChannel(BaseModel):
    title: str
    author: str
    subtitle: str
    url: str
    description: str
    image: str

    @classmethod
    def from_ytdlp(cls, data: dict[str, Any], url: str) -> "RssChannel":
        """Create RssChannel directly from yt-dlp extract_info response."""
        title = data.get("uploader") or data.get("title", "")
        author = data.get("uploader_id", "YouTube")
        description = data.get("description", "")

        # Extract image from avatar or thumbnails
        avatar_data = data.get("avatar")
        thumbnail_data = data.get("thumbnails")
        image = cls._extract_image(avatar_data) or cls._extract_image(thumbnail_data)

        return cls(
            title=title,
            author=author,
            subtitle="",
            url=url,
            description=description,
            image=image,
        )

    @staticmethod
    def _extract_image(data: Any) -> str:
        """Extract image URL from avatar/thumbnails data (list or string)."""
        if not data:
            return ""
        if isinstance(data, list):
            return _extract_image_from_list(data)
        if isinstance(data, str):
            return data
        return ""


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

    @classmethod
    def from_ytdlp(cls, data: dict[str, Any], author: str) -> "RssEpisode":
        """Create RssEpisode from yt-dlp video entry dict."""
        video_id = data.get("id", "")
        title = data.get("title", "")
        description = data.get("description")
        duration = data.get("duration")
        availability = data.get("availability", "public")

        # Construct YouTube URL
        url = data.get("url") or f"https://youtube.com/watch?v={video_id}"

        episode = cls(
            id=video_id,
            title=title,
            author=author,
            description=description,
            content=url,
            duration=duration,
        )

        # Store availability for filtering
        episode._availability = availability

        return episode

    @property
    def is_public(self) -> bool:
        """Check if video is publicly available."""
        return self._availability in (None, "public")
