from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.utils.text import create_slug


def _exclude_lookahead(pattern: str) -> str:
    if pattern.startswith("^"):
        return f"(?!{pattern[1:]})"
    return f"(?!.*{pattern})"


def _include_lookahead(patterns: list[str]) -> str | None:
    if not patterns:
        return None
    return f"(?=.*(?:{'|'.join(patterns)}))"


class SourceFilter(BaseModel):
    """Structured filter rules for podcast episode selection."""

    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    r_rules: list[str] = Field(default_factory=list)

    def _regex_parts(self) -> list[str]:
        parts: list[str] = ["(?i)^"]
        parts.extend(_exclude_lookahead(pattern) for pattern in self.exclude)
        include_part = _include_lookahead(self.include)
        if include_part:
            parts.append(include_part)
        parts.append(".*$")
        return parts

    def to_regex(self) -> str | None:
        if not (self.include or self.exclude):
            return None
        return "".join(self._regex_parts())


class FeedSource(BaseModel):
    """A single URL source with optional per-source filter rules."""

    model_config = ConfigDict(extra="forbid")

    url: str
    filters: SourceFilter = Field(default_factory=SourceFilter)


class PodcastConfig(BaseModel):
    """Configuration for a single podcast series."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    references: list[FeedSource] = Field(default_factory=list)
    downloads: list[FeedSource] = Field(default_factory=list)
    schedule: list[str] = Field(default_factory=list)

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return create_slug(self.name)


def ensure_source_filter(filters: SourceFilter | dict[str, Any] | None) -> SourceFilter:
    if isinstance(filters, SourceFilter):
        return filters
    if filters is None:
        return SourceFilter()
    return SourceFilter.model_validate(filters)


def ensure_feed_source(source: FeedSource | dict[str, Any]) -> FeedSource:
    if isinstance(source, FeedSource):
        return source
    try:
        payload = dict(source)
    except Exception as exc:
        raise TypeError("source must be FeedSource or dict") from exc
    payload["filters"] = ensure_source_filter(payload.get("filters"))
    return FeedSource.model_validate(payload)


def ensure_podcast_config(podcast: PodcastConfig | dict[str, Any]) -> PodcastConfig:
    def _ensure_sources_list(raw_sources: Any) -> list[FeedSource]:
        if raw_sources is None:
            return []
        if not isinstance(raw_sources, list):
            raise TypeError("references/downloads must be a list")
        typed_sources = cast(list[FeedSource | dict[str, Any]], raw_sources)
        return [ensure_feed_source(item) for item in typed_sources]

    if isinstance(podcast, PodcastConfig):
        return podcast
    payload = dict(podcast)
    payload["references"] = _ensure_sources_list(payload.get("references"))
    payload["downloads"] = _ensure_sources_list(payload.get("downloads"))
    if "path" not in payload:
        payload["path"] = f"/media/podcasts/{create_slug(payload['name'])}"
    return PodcastConfig.model_validate(payload)


def parse_podcasts_raw(raw: list[PodcastConfig | dict[str, Any]]) -> list[PodcastConfig]:
    return [ensure_podcast_config(entry) for entry in raw]
