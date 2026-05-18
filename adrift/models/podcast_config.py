import re
from functools import lru_cache
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, computed_field
from unidecode import unidecode


@lru_cache(maxsize=1000)
def _slug(name: str) -> str:
    text = re.sub(r"(?i)\.[a-z34]+$", "", name)
    text = unidecode(text).lower()
    text = re.sub(r"([a-z]+)_s\b", r"\1's", text)
    text = re.sub(r"\b([a-z]+)'([a-z]{1,2})\b", r"\1\2", text)
    text = text.replace(" ", "-").replace("_", "-")
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:100]


_ModelT = TypeVar("_ModelT", bound=BaseModel)


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


class ScoringWeights(BaseModel):
    """Alignment signal weights for title/date/description/id scoring."""

    model_config = ConfigDict(extra="forbid")

    id: float = 0.10
    date: float = 0.30
    title: float = 0.50
    description: float = 0.10


class AlignmentConfig(BaseModel):
    """Per-podcast alignment tuning knobs."""

    model_config = ConfigDict(extra="forbid")

    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    date_score_tiers: list[tuple[int, float]] = Field(
        default_factory=lambda: [(2, 1.00), (10, 0.70), (35, 0.15)]
    )
    sparse_title_min: float = 0.85
    match_tolerance: float = 0.75
    extra_stopwords: list[str] = Field(default_factory=list)


class PodcastConfig(BaseModel):
    """Configuration for a single podcast series."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    references: list[FeedSource] = Field(default_factory=list)
    downloads: list[FeedSource] = Field(default_factory=list)
    schedule: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    alignment: AlignmentConfig = Field(default_factory=AlignmentConfig)

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return _slug(self.name)


def _ensure_model(value: Any, cls: type[_ModelT], **defaults: Any) -> _ModelT:
    if isinstance(value, cls):
        return value
    if value is None:
        return cls.model_validate(defaults)
    if isinstance(value, dict):
        return cls.model_validate({**defaults, **value})
    raise TypeError(f"value must be {cls.__name__}, dict, or None")


def ensure_source_filter(filters: SourceFilter | dict[str, Any] | None) -> SourceFilter:
    return _ensure_model(filters, SourceFilter)


def ensure_feed_source(source: FeedSource | dict[str, Any]) -> FeedSource:
    if isinstance(source, FeedSource):
        return source
    if not isinstance(source, dict):
        raise TypeError("source must be FeedSource or dict")
    payload = dict(source)
    payload["filters"] = ensure_source_filter(payload.get("filters"))
    return _ensure_model(payload, FeedSource)


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
    if not isinstance(podcast, dict):
        raise TypeError("podcast must be PodcastConfig or dict")
    payload = dict(podcast)
    payload["references"] = _ensure_sources_list(payload.get("references"))
    payload["downloads"] = _ensure_sources_list(payload.get("downloads"))
    payload["tags"] = payload.get("tags", [])
    if "path" not in payload:
        payload["path"] = f"/media/podcasts/{_slug(payload['name'])}"
    return _ensure_model(payload, PodcastConfig)


def parse_podcasts_raw(raw: list[PodcastConfig]) -> list[PodcastConfig]:
    return [ensure_podcast_config(entry) for entry in raw]
