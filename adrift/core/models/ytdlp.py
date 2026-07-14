# cspell: words preferredcodec preferredquality postprocessors
"""Typed pydantic wrappers over yt-dlp's permissive ``extract_info`` dicts."""

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, field_validator


class YtDlpImage(BaseModel):
    """Typed image/thumbnail entry in yt-dlp payloads."""

    url: str | None = None
    width: int | None = None
    height: int | None = None

    model_config = ConfigDict(extra="allow")


class YtDlpPostprocessor(BaseModel):
    """Typed postprocessor entry in yt-dlp options/payloads."""

    key: str | None = None
    preferredcodec: str | None = None
    preferredquality: str | None = None

    model_config = ConfigDict(extra="allow")


def _dict_items_or_none(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    return [
        cast("dict[str, Any]", item) for item in cast("list[Any]", value) if isinstance(item, dict)
    ]


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
    thumbnails: list[YtDlpImage] | None = None
    avatar: list[YtDlpImage] | str | None = None
    upload_date: str | None = None
    timestamp: int | float | None = None
    release_timestamp: int | float | None = None
    availability: str | None = None
    postprocessors: list[YtDlpPostprocessor] | None = None
    js_runtimes: dict[str, dict[str, Any]] | None = None
    extractor_args: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("thumbnails", mode="before")
    @classmethod
    def _coerce_thumbnails(cls, value: object) -> list[dict[str, Any]] | None:
        return _dict_items_or_none(value)

    @field_validator("avatar", mode="before")
    @classmethod
    def _coerce_avatar(cls, value: object) -> list[dict[str, Any]] | str | None:
        if isinstance(value, str):
            return value
        return _dict_items_or_none(value)

    @field_validator("postprocessors", mode="before")
    @classmethod
    def _coerce_postprocessors(cls, value: object) -> list[dict[str, Any]] | None:
        return _dict_items_or_none(value)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401 -- mirrors the raw yt-dlp dict
        """Return ``key`` via attribute access, falling back to the dumped dict."""
        # Allow mapping-style access for backward compatibility with code
        # that indexes into the raw yt-dlp dicts.
        return getattr(self, key, self.model_dump().get(key))

    def __setitem__(self, key: str, value: object) -> None:
        """Set ``key`` to ``value`` via attribute access, validating on failure."""
        try:
            setattr(self, key, value)
        except (AttributeError, TypeError, ValueError):
            data = self.model_dump()
            data[key] = value
            self.model_validate(data)
