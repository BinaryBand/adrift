# cspell: ignore-word rrulestr
import glob
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import tomllib
from dateutil.rrule import rrulestr

from src.config import MATCH_TOLERANCE
from src.models import (
    FeedSource,
    PodcastConfig,
    SourceFilter,
    ensure_feed_source,
    ensure_podcast_config,
    ensure_source_filter,
    parse_podcasts_raw,
)

__all__ = [
    "MATCH_TOLERANCE",
    "SourceFilter",
    "FeedSource",
    "PodcastConfig",
    "ensure_source_filter",
    "ensure_feed_source",
    "ensure_podcast_config",
    "parse_podcasts_raw",
    "load_config",
    "load_podcasts_config",
    "schedule_matches_today",
]


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
    configs = parse_podcasts_raw(cast(list[PodcastConfig], podcasts_raw))
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
            matches = sorted(glob.glob(target))
            head, tail = os.path.split(target)
            if tail and not tail.startswith("."):
                hidden_target = os.path.join(head, f".{tail}") if head else f".{tail}"
                matches.extend(sorted(glob.glob(hidden_target)))
            targets.extend(list(dict.fromkeys(matches)))
        else:
            targets.append(target)
    return targets
