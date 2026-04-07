import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast

import pydantic
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict

# Ensure project root is on sys.path when executed as script
sys.path.insert(0, Path(__file__).parent.parent.as_posix())
load_dotenv(find_dotenv())
DEVICE = os.getenv("DEVICE", "UnknownDevice")
PROJECT = os.getenv("PROJECT", "UnknownProject")


class S3Metadata(pydantic.BaseModel, ABC):
    """Abstract base class for S3 metadata models."""

    uploader: str | None = pydantic.Field(default=DEVICE, description="Device identifier")

    @abstractmethod
    def to_dict(self) -> dict[str, str]:
        """Convert to S3-compatible metadata dictionary (all string values)."""
        pass


class CacheMetadata(S3Metadata):
    """S3 object metadata for cached items."""

    created_at: datetime = pydantic.Field(description="Creation timestamp")
    expires_at: datetime | None = pydantic.Field(default=None, description="Expiration timestamp")

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
    if not data:
        return ""

    last = data[-1]
    if isinstance(last, dict):
        last_dict = cast(dict[str, Any], last)
        try:
            url = last_dict["url"]
        except Exception:
            return ""

        if isinstance(url, str):
            return url

    return ""


def _from_unix_timestamp(raw: Any) -> datetime | None:
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str) and raw.isdigit():
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    return None


def _parse_upload_date(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _coalesce_str(*values: Any) -> str:
    """Return the first truthy value as a string, or empty string.

    This helper centralises simple fallback chains into one place so
    that small methods using multiple `or` fallbacks have reduced
    cyclomatic complexity.
    """
    for v in values:
        if v:
            return str(v)
    return ""


try:
    from .ytdlp import YtDlpVideo
except Exception:
    # When executed as a script the package-relative import may fail;
    # fall back to absolute import using the `src` package on sys.path.
    from src.models.ytdlp import YtDlpVideo


def _parse_ytdlp_pub_date(data: YtDlpVideo | dict[str, Any]) -> datetime | None:
    # Accept either a validated YtDlpVideo model or a raw dict and
    # normalise to a mapping for existing parsing helpers.
    mapping: dict[str, Any]
    if isinstance(data, YtDlpVideo):
        mapping = data.model_dump()
    else:
        mapping = data

    for key in ("timestamp", "release_timestamp"):
        if dt := _from_unix_timestamp(mapping.get(key)):
            return dt
    return _parse_upload_date(mapping.get("upload_date"))


def _ensure_ytdlp_model(data: YtDlpVideo | dict[str, Any]) -> YtDlpVideo:
    if isinstance(data, YtDlpVideo):
        return data
    return YtDlpVideo.model_validate(data)


class RssChannel(BaseModel):
    title: str
    author: str
    subtitle: str
    url: str
    description: str
    image: str

    @classmethod
    def from_ytdlp(cls, data: YtDlpVideo | dict[str, Any], url: str) -> "RssChannel":
        """Create RssChannel directly from yt-dlp extract_info response.

        Accepts either a raw dict (validated into `YtDlpVideo`) or an
        already-validated `YtDlpVideo` instance.
        """
        model = _ensure_ytdlp_model(data)
        return cls._from_model(model, url)

    @classmethod
    def _from_model(cls, model: YtDlpVideo, url: str) -> "RssChannel":
        return cls(
            title=_coalesce_str(model.uploader, model.title),
            author=_coalesce_str(model.uploader_id, "YouTube"),
            subtitle="",
            url=url,
            description=_coalesce_str(model.description),
            image=_coalesce_str(
                cls._extract_image(model.avatar), cls._extract_image(model.thumbnails)
            ),
        )

    @staticmethod
    def _extract_image(data: Any) -> str:
        """Extract image URL from avatar/thumbnails data (list or string)."""
        if not data:
            return ""
        if isinstance(data, list):
            return _extract_image_from_list(cast(list[Any], data))
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
    def from_ytdlp(cls, data: YtDlpVideo | dict[str, Any], author: str) -> "RssEpisode":
        """Create RssEpisode from yt-dlp video entry dict or model."""
        model = _ensure_ytdlp_model(data)
        return cls._from_model(model, author)

    @classmethod
    def _from_model(cls, model: YtDlpVideo, author: str) -> "RssEpisode":
        video_id = _coalesce_str(model.id)
        title = _coalesce_str(model.title)
        description = model.description
        duration = model.duration
        availability = _coalesce_str(model.availability, "public")

        # Construct YouTube URL
        url = _coalesce_str(model.url, f"https://youtube.com/watch?v={video_id}")

        episode = cls(
            id=video_id,
            title=title,
            author=author,
            description=description,
            content=url,
            duration=duration,
            pub_date=_parse_ytdlp_pub_date(model),
        )

        # Store availability for filtering
        episode._availability = availability

        return episode

    @property
    def is_public(self) -> bool:
        """Check if video is publicly available."""
        return self._availability in (None, "public")
