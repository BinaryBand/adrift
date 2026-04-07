# cspell: ignore-word rrulestr
import glob
import random
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import tomllib
from dateutil.rrule import rrulestr
from pydantic import BaseModel, ConfigDict, computed_field

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from datetime import datetime, timedelta

from src.files.s3 import S3_ENDPOINT
from src.utils.text import create_slug

MATCH_TOLERANCE = 0.75


def _exclude_lookahead(pattern: str) -> str:
    if pattern.startswith("^"):
        return f"(?!{pattern[1:]})"
    return f"(?!.*{pattern})"


def _include_lookahead(patterns: list[str]) -> str | None:
    if not patterns:
        return None
    return f"(?=.*(?:{'|'.join(patterns)}))"


def _day_window(current: datetime) -> tuple[datetime, datetime]:
    day_start = datetime.combine(current.date(), datetime.min.time())
    return day_start, day_start + timedelta(days=1)


def _align_tz(reference: datetime, target: datetime) -> datetime:
    state = (reference.tzinfo is None, target.tzinfo is None)
    if state == (False, True):
        return target.replace(tzinfo=reference.tzinfo)
    if state == (True, False):
        return target.replace(tzinfo=None)
    return target


def _next_occurrence_in_window(schedule: str, day_start: datetime) -> datetime | None:
    # Support RFC5545 forms like:
    #   DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=MO
    # For bare RRULE values, seed dtstart from the day window as before.
    if "DTSTART" in schedule.upper():
        rule = rrulestr(schedule)
        rule_start = getattr(rule, "_dtstart", None)
        if isinstance(rule_start, datetime):
            day_start = _align_tz(rule_start, day_start)
    else:
        rule = rrulestr(schedule, dtstart=day_start)
    return rule.after(day_start - timedelta(microseconds=1), inc=True)


class SourceFilter(BaseModel):
    """Structured filter rules for podcast episode selection.

    Patterns in ``include`` and ``exclude`` are standard Python regex
    strings matched with ``re.search()`` (case-insensitive by default
    via ``to_regex()``).  ``r_rules`` is a list of RFC 5545 RRULE strings
    (e.g. ``"FREQ=WEEKLY;BYDAY=MO"``) used to restrict episodes to those
    published on days matching any of the given recurrence rules.
    """

    model_config = ConfigDict(extra="forbid")

    include: list[str] = []
    exclude: list[str] = []
    r_rules: list[str] = []

    def _regex_parts(self) -> list[str]:
        parts: list[str] = ["(?i)^"]
        parts.extend(_exclude_lookahead(pattern) for pattern in self.exclude)
        include_part = _include_lookahead(self.include)
        if include_part:
            parts.append(include_part)
        parts.append(".*$")
        return parts

    def to_regex(self) -> str | None:
        """Compile include/exclude rules to a case-insensitive search regex."""
        if not (self.include or self.exclude):
            return None
        return "".join(self._regex_parts())


class FeedSource(BaseModel):
    """A single URL source with optional per-source filter rules."""

    model_config = ConfigDict(extra="forbid")

    url: str
    filters: SourceFilter = SourceFilter()


class PodcastConfig(BaseModel):
    """Configuration for a single podcast series."""

    model_config = ConfigDict(extra="ignore")

    name: str
    references: list[FeedSource] = []
    downloads: list[FeedSource] = []

    @computed_field(return_type=str)
    def slug(self) -> str:
        return create_slug(self.name)

    @computed_field(return_type=str)
    def path(self) -> str:
        return f"/media/podcasts/{self.slug}"

    # iCalendar RRULE strings that control when downloads run, e.g.
    # ["FREQ=WEEKLY;BYDAY=WE,FR"].  Empty list = always run.
    schedule: list[str] = []

    @computed_field(return_type=str)
    def link(self) -> str:
        return urljoin(S3_ENDPOINT, self.path + ".rss")


def ensure_source_filter(filters: SourceFilter | dict[str, Any] | None) -> SourceFilter:
    if isinstance(filters, SourceFilter):
        return filters
    if filters is None:
        return SourceFilter()
    if isinstance(filters, dict):
        return SourceFilter.model_validate(filters)
    raise TypeError("filters must be SourceFilter, dict, or None")


def ensure_feed_source(source: FeedSource | dict[str, Any]) -> FeedSource:
    if isinstance(source, FeedSource):
        return source
    if isinstance(source, dict):
        payload = dict(source)
        payload["filters"] = ensure_source_filter(payload.get("filters"))
        return FeedSource.model_validate(payload)
    raise TypeError("source must be FeedSource or dict")


def ensure_podcast_config(podcast: PodcastConfig | dict[str, Any]) -> PodcastConfig:
    if isinstance(podcast, PodcastConfig):
        return podcast
    if isinstance(podcast, dict):
        payload = dict(podcast)
        for key in ("references", "downloads"):
            raw_sources = payload.get(key, [])
            if raw_sources is None:
                payload[key] = []
                continue
            if not isinstance(raw_sources, list):
                raise TypeError(f"{key} must be a list")
            payload[key] = [ensure_feed_source(item) for item in raw_sources]
        return PodcastConfig.model_validate(payload)
    raise TypeError("podcast must be PodcastConfig or dict")


def parse_podcasts_raw(raw: list[PodcastConfig | dict[str, Any]]) -> list[PodcastConfig]:
    return [ensure_podcast_config(entry) for entry in raw]


def _load_config(name_or_path: str) -> list[PodcastConfig]:
    """Load podcast configurations from a TOML file.

    Accepts either a bare config name (e.g. ``"podcasts"``) which is
    resolved to ``config/<name>.toml`` relative to the project root, or
    a full/relative file path ending in ``.toml``.
    """
    path = Path(name_or_path)
    if not path.suffix:
        # Resolve short name → config/<name>.toml
        path = Path("config") / f"{name_or_path}.toml"

    with open(path, "rb") as f:
        data = tomllib.load(f)

    podcasts_raw = data.get("podcasts", [])
    if not isinstance(podcasts_raw, list):
        return []
    configs = parse_podcasts_raw(podcasts_raw)
    random.shuffle(configs)
    return configs


def _schedule_matches_today(schedule: str, title: str, today: datetime | None = None) -> bool:
    """Return True if *schedule* yields an occurrence within today's day window."""
    del title
    current = today or datetime.now()
    day_start, day_end = _day_window(current)

    try:
        next_occurrence = _next_occurrence_in_window(schedule, day_start)
        if next_occurrence is None:
            return False
        day_end = _align_tz(next_occurrence, day_end)
        return next_occurrence < day_end
    except Exception:
        # Fail closed: if RRULE is malformed we skip this schedule.
        return False


def _config_schedule_matches_today(config: "PodcastConfig") -> bool:
    # """Return True if any RRULE in config.schedule matches today, or if schedule is empty."""
    # if not config.schedule:
    #     return True
    # return any(_schedule_matches_today(rule, config.name) for rule in config.schedule)
    return True


def load_podcasts_config(include: list[str]) -> list[PodcastConfig]:
    """Load and schedule-filter podcast configurations.

    *include* is a list of config names or file paths passed to
    :func:`_load_config`.  Entries whose ``schedule`` RRULE does not
    match today are excluded.
    """
    targets = _expand_include_targets(include)
    configs: list[PodcastConfig] = [c for t in targets for c in _load_config(t)]

    # Filter configs by schedule and return (shuffle to randomize order)
    filtered: list[PodcastConfig] = [it for it in configs if _config_schedule_matches_today(it)]
    random.shuffle(filtered)
    return filtered


def _expand_include_targets(include: list[str]) -> list[str]:
    """Expand shell-style glob patterns in the include list to concrete paths.

    This helper centralizes glob expansion and keeps the public API simple
    and easier to test.
    """
    targets: list[str] = []
    for target in include:
        if any(ch in target for ch in ("*", "?", "[")):
            targets.extend(sorted(glob.glob(target)))
        else:
            targets.append(target)
    return targets


def load_static_config(filename: str) -> dict[str, Any]:
    """Load a static TOML configuration file from the ``config/`` directory.

    Falls back gracefully and returns an empty dict when the file is
    missing or malformed.
    """
    config_path = Path(__file__).parent.parent / "config" / filename
    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
            assert isinstance(raw, dict), "Config file must contain a TOML table"
            return raw
    except (FileNotFoundError, tomllib.TOMLDecodeError) as e:
        print(f"WARNING: Could not load {filename}: {e}")
        return {}
