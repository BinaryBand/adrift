from pydantic import BaseModel, ConfigDict, computed_field
from urllib.parse import urljoin
from pathlib import Path
from dateutil.rrule import rrulestr

import tomllib
import random
import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.files.s3 import S3_ENDPOINT
from datetime import datetime, timedelta


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


def _next_occurrence_in_window(schedule: str, day_start: datetime) -> datetime | None:
    # Support RFC5545 forms like:
    #   DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=MO
    # For bare RRULE values, seed dtstart from the day window as before.
    if "DTSTART" in schedule.upper():
        rule = rrulestr(schedule)
        rule_start = getattr(rule, "_dtstart", None)
        if isinstance(rule_start, datetime):
            if rule_start.tzinfo is not None and day_start.tzinfo is None:
                day_start = day_start.replace(tzinfo=rule_start.tzinfo)
            if rule_start.tzinfo is None and day_start.tzinfo is not None:
                day_start = day_start.replace(tzinfo=None)
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

    def to_regex(self) -> str | None:
        """Compile include/exclude lists into a single regex string.

        The generated pattern is designed for ``re.search()``.  It is
        case-insensitive and combines:

        * Negative look-ahead for every ``exclude`` entry so that any
          title containing that pattern is rejected.
        * A positive look-ahead for the union of all ``include`` entries
          so that the title must match at least one (when ``include`` is
          non-empty).
        """
        if not self.include and not self.exclude:
            return None

        parts: list[str] = ["(?i)^"]

        parts.extend(_exclude_lookahead(pattern) for pattern in self.exclude)
        if include_part := _include_lookahead(self.include):
            parts.append(include_part)

        parts.append(".*$")
        return "".join(parts)


class FeedSource(BaseModel):
    """A single URL source with optional per-source filter rules."""

    model_config = ConfigDict(extra="forbid")

    url: str
    filters: SourceFilter = SourceFilter()


class PodcastConfig(BaseModel):
    """Configuration for a single podcast series."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    references: list[FeedSource] = []
    downloads: list[FeedSource] = []

    # iCalendar RRULE strings that control when downloads run, e.g.
    # ["FREQ=WEEKLY;BYDAY=WE,FR"].  Empty list = always run.
    schedule: list[str] = []

    @computed_field(return_type=str)
    def link(self) -> str:
        return urljoin(S3_ENDPOINT, self.path + ".rss")


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

    podcasts_raw: list[dict] = data.get("podcasts", [])
    configs = [PodcastConfig.model_validate(entry) for entry in podcasts_raw]
    random.shuffle(configs)
    return configs


def _schedule_matches_today(
    schedule: str, title: str, today: datetime | None = None
) -> bool:
    """Return True if the RRULE *schedule* includes today.

    Uses ``dateutil.rrule`` to evaluate whether the rule produces at
    least one occurrence within today's local day window.

    Examples::

        "FREQ=WEEKLY;BYDAY=WE,FR"  →  True on Wednesdays and Fridays
    """
    del title
    current = today or datetime.now()
    day_start, day_end = _day_window(current)

    try:
        next_occurrence = _next_occurrence_in_window(schedule, day_start)
        if next_occurrence is None:
            return False
        if next_occurrence.tzinfo is not None and day_end.tzinfo is None:
            day_end = day_end.replace(tzinfo=next_occurrence.tzinfo)
        if next_occurrence.tzinfo is None and day_end.tzinfo is not None:
            day_end = day_end.replace(tzinfo=None)
        return next_occurrence is not None and next_occurrence < day_end
    except Exception:
        # Fail closed: if RRULE is malformed we skip this schedule.
        return False


def _config_schedule_matches_today(config: "PodcastConfig") -> bool:
    """Return True if any RRULE in config.schedule matches today, or if schedule is empty."""
    if not config.schedule:
        return True
    return any(_schedule_matches_today(rule, config.name) for rule in config.schedule)


def load_podcasts_config(include: list[str]) -> list[PodcastConfig]:
    """Load and schedule-filter podcast configurations.

    *include* is a list of config names or file paths passed to
    :func:`_load_config`.  Entries whose ``schedule`` RRULE does not
    match today are excluded.
    """
    configs: list[PodcastConfig] = []
    for target in include:
        configs.extend(_load_config(target))

    filtered: list[PodcastConfig] = []
    for it in configs:
        if not _config_schedule_matches_today(it):
            continue
        filtered.append(it)

    return filtered


def load_static_config(filename: str) -> dict:
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
