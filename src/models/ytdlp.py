from typing import Any

from pydantic import BaseModel, ConfigDict


class YtDlpVideo(BaseModel):
    """Pydantic model representing a subset of yt-dlp `extract_info` video dict.

    This model is intentionally permissive (`extra="allow"`) so it can be
    used as a drop-in replacement for untyped dicts returned by yt-dlp while
    giving the codebase a typed surface to narrow over time.
    """

    id: str | None = None
    title: str | None = None
    uploader: str | None = None
    uploader_id: str | None = None
    description: str | None = None
    duration: float | None = None
    url: str | None = None
    thumbnails: list[dict[str, Any]] | None = None
    avatar: list[dict[str, Any]] | str | None = None
    upload_date: str | None = None
    timestamp: int | float | None = None
    release_timestamp: int | float | None = None
    availability: str | None = None
    postprocessors: list[dict[str, Any]] | None = None
    js_runtimes: dict[str, dict[str, Any]] | None = None
    extractor_args: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    def __getitem__(self, key: str) -> Any:
        # Allow mapping-style access for backward compatibility with code
        # that indexes into the raw yt-dlp dicts.
        return getattr(self, key, self.model_dump().get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            setattr(self, key, value)
        except Exception:
            data = self.model_dump()
            data[key] = value
            self.model_validate(data)
