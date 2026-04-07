from typing import Any

from pydantic import BaseModel, ConfigDict


class FeedSource(BaseModel):
    """Model representing a single download source entry under a podcast.

    This model is intentionally permissive (`extra="allow"`) to allow a
    smooth migration from untyped dicts in TOML to a typed surface.
    """

    url: str | None = None
    filters: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class PodcastConfig(BaseModel):
    """Top-level podcast configuration containing metadata and downloads."""

    name: str | None = None
    downloads: list[FeedSource] | None = None

    model_config = ConfigDict(extra="allow")
