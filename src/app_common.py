# cspell: ignore-word rrulestr
import glob
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import tomllib
from dateutil.rrule import rrulestr
from pydantic import BaseModel, ConfigDict, computed_field

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
    # ["FREQ=WEEKLY;BYDAY=WE,FR"]. Empty list = always include.
    schedule: list[str] = []


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
    return PodcastConfig.model_validate(payload)


def parse_podcasts_raw(
    raw: list[PodcastConfig | dict[str, Any]],
) -> list[PodcastConfig]:
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
    configs = parse_podcasts_raw(cast(list[PodcastConfig | dict[str, Any]], podcasts_raw))
    random.shuffle(configs)
    return configs


def schedule_matches_today(schedule: str, title: str, today: datetime | None = None) -> bool:
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


_schedule_matches_today = schedule_matches_today


def load_config(name_or_path: str) -> list[PodcastConfig]:
    return _load_config(name_or_path)


def _config_schedule_matches_today(config: "PodcastConfig") -> bool:
    """Return True if any RRULE in config.schedule matches today, or if schedule is empty."""
    if not config.schedule:
        return True
    return any(_schedule_matches_today(rule, config.name) for rule in config.schedule)


def _load_configs_for_targets(targets: list[str]) -> list[PodcastConfig]:
    return [config for target in targets for config in _load_config(target)]


def _schedule_filtered_configs(configs: list[PodcastConfig]) -> list[PodcastConfig]:
    return [config for config in configs if _config_schedule_matches_today(config)]


def load_podcasts_config(
    include: list[str], skip_schedule_filter: bool = False
) -> list[PodcastConfig]:
    """Load podcast configurations, optionally filtering by schedule.

    *include* is a list of config names or file paths passed to
    :func:`_load_config`. Entries whose ``schedule`` RRULE does not
    match today are excluded unless ``skip_schedule_filter`` is true.
    """
    configs = _load_configs_for_targets(_expand_include_targets(include))

    if skip_schedule_filter:
        random.shuffle(configs)
        return configs

    filtered = _schedule_filtered_configs(configs)
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
