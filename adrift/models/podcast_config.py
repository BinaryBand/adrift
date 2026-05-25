import json
import re
from functools import lru_cache
from pathlib import Path
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


class TitleNormalizationReplacement(BaseModel):
    """Regex replacement rule for title/slug normalization."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    replacement: str = ""
    target: str = "title"


class TitleNormalizationConfig(BaseModel):
    """Per-podcast cleanup rules for title normalization."""

    model_config = ConfigDict(extra="forbid")

    prefix_patterns: list[str] = Field(default_factory=list)
    suffix_patterns: list[str] = Field(default_factory=list)
    slug_suffixes: list[str] = Field(default_factory=list)
    replacements: list[TitleNormalizationReplacement] = Field(default_factory=list)


class CleanupConfig(BaseModel):
    """Per-podcast cleanup behavior settings."""

    model_config = ConfigDict(extra="forbid")

    title_normalization: TitleNormalizationConfig = Field(default_factory=TitleNormalizationConfig)


class _PodcastConfigBase(BaseModel):
    """Shared podcast config fields used by runtime and TOML input models."""

    model_config = ConfigDict(extra="forbid")

    name: str
    references: list[FeedSource] = Field(default_factory=list)
    downloads: list[FeedSource] = Field(default_factory=list)
    schedule: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    alignment: AlignmentConfig = Field(default_factory=AlignmentConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)


class PodcastConfig(_PodcastConfigBase):
    """Configuration for a single podcast series."""

    path: str

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return _slug(self.name)


class PodcastConfigInput(_PodcastConfigBase):
    """Input-only podcast config shape as authored in TOML files."""

    path: str | None = None


class PodcastsTomlConfig(BaseModel):
    """Top-level TOML config document consumed by app_common.load_config."""

    model_config = ConfigDict(extra="forbid")

    podcasts: list[PodcastConfigInput] = Field(default_factory=list)


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


def podcast_toml_json_schema() -> dict[str, Any]:
    """Return JSON Schema for config/*.toml validation in editors and CI tooling."""
    schema = PodcastsTomlConfig.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


def compile_podcast_toml_schema(
    output_path: str | Path = "adrift/models/podcasts.schema.json",
) -> Path:
    """Compile and write TOML JSON Schema used by Even Better TOML."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(podcast_toml_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out
