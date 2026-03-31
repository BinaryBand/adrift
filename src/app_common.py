from pydantic import BaseModel, computed_field
from urllib.parse import urljoin
from functools import cache
from typing import Literal
from pathlib import Path

import tomllib
import pandas as pd
import hashlib
import random
import ast
import re
import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.models import DEVICE
from src.files.s3 import S3_ENDPOINT
from datetime import datetime
from src.utils.text import create_slug


DAY_OF_WEEK = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
LOG_PATH = Path(".logs") / DEVICE
MATCH_TOLERANCE = 0.75

# Maps iCalendar RRULE BYDAY codes to three-letter day names used throughout
_RRULE_BYDAY: dict[str, DAY_OF_WEEK] = {
    "MO": "mon",
    "TU": "tue",
    "WE": "wed",
    "TH": "thu",
    "FR": "fri",
    "SA": "sat",
    "SU": "sun",
}


class MatchData(BaseModel):
    file: str | None
    episode: str | None
    score: float


class FilterRules(BaseModel):
    """Structured filter rules for podcast episode selection.

    Patterns in ``include`` and ``exclude`` are standard Python regex
    strings matched with ``re.search()`` (case-insensitive by default
    via ``to_regex()``).  ``publish_days`` restricts episodes to those
    published on the given days of the week.
    """

    include: list[str] = []
    exclude: list[str] = []
    publish_days: list[DAY_OF_WEEK] = []

    def to_regex(self) -> str | None:
        """Compile include/exclude lists into a single regex string.

        The generated pattern is designed for ``re.search()``.  It is
        case-insensitive and combines:

        * Negative lookaheads for every ``exclude`` entry so that any
          title containing that pattern is rejected.
        * A positive lookahead for the union of all ``include`` entries
          so that the title must match at least one (when ``include`` is
          non-empty).
        """
        if not self.include and not self.exclude:
            return None

        parts: list[str] = ["(?i)^"]

        for pattern in self.exclude:
            if pattern.startswith("^"):
                # Anchored at the start of the title – no leading .*
                parts.append(f"(?!{pattern[1:]})")
            else:
                parts.append(f"(?!.*{pattern})")

        if self.include:
            inc_parts = "|".join(self.include)
            parts.append(f"(?=.*(?:{inc_parts}))")

        parts.append(".*$")
        return "".join(parts)


class PodcastData(BaseModel):
    """Configuration for a single podcast series."""

    title: str
    path: str
    feeds: list[str]
    sources: list[str]

    # Structured filter rules (replace the old flat regex string fields).
    # ``filters`` is the default applied to both feeds and sources.
    # ``feed_filters`` / ``source_filters`` override ``filters`` when set.
    filters: FilterRules = FilterRules()
    feed_filters: FilterRules | None = None
    source_filters: FilterRules | None = None

    # iCalendar RRULE string that controls when downloads run, e.g.
    # "FREQ=WEEKLY;BYDAY=WE,FR".  Omit BYDAY to use a deterministic
    # per-show day derived from the title hash.
    schedule: str | None = None

    @computed_field(return_type=str)
    def link(self) -> str:
        return urljoin(S3_ENDPOINT, self.path + ".rss")

    @computed_field(return_type=list[MatchData])
    def log_data(self) -> list[MatchData]:
        return get_match_data(self.title)


def get_match_data(title: str) -> list[MatchData]:
    df_label = f"{create_slug(title)}_match"
    match_path = (
        Path(".log") / DEVICE / datetime.now().strftime("%Y-%m-%d") / f"{df_label}.csv"
    )

    if not match_path.exists():
        return []

    df = pd.read_csv(match_path)

    # Preferred format: real columns written by _update_logs.
    if {"file", "episode", "score"}.issubset(set(df.columns)):
        _out: list[MatchData] = []
        for row in df.to_dict(orient="records"):
            file = row.get("file")
            episode = row.get("episode")
            score = row.get("score", 0.0)
            _out.append(
                MatchData(
                    file=None if pd.isna(file) else str(file),
                    episode=None if pd.isna(episode) else str(episode),
                    score=0.0 if pd.isna(score) else float(score),
                )
            )
        return _out

    # Back-compat: older CSVs where each row is 3 columns containing
    # stringified tuples like "('file', '...')", "('episode', '...')".
    tuple_cols = [c for c in df.columns if c != "Unnamed: 0"]
    out: list[MatchData] = []
    for row in df.to_dict(orient="records"):
        parsed: dict[str, object] = {}
        for col in tuple_cols:
            cell = row.get(col)
            if not isinstance(cell, str):
                continue
            try:
                k, v = ast.literal_eval(cell)
            except Exception:
                continue
            if isinstance(k, str):
                parsed[k] = v

        file = parsed.get("file")
        episode = parsed.get("episode")
        _score = parsed.get("score", 0.0)
        score = float(_score) if isinstance(_score, (int, float, str)) else 0.0
        out.append(
            MatchData(
                file=None if file is None else str(file),
                episode=None if episode is None else str(episode),
                score=score,
            )
        )

    return out


def _load_config(name_or_path: str) -> list[PodcastData]:
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
    configs = [PodcastData.model_validate(entry) for entry in podcasts_raw]
    random.shuffle(configs)
    return configs


@cache
def _get_deterministic_day(title: str) -> DAY_OF_WEEK:
    """Assign a deterministic day of the week based on the title."""
    day_of_week_it: list[DAY_OF_WEEK] = [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]
    normalized = title.strip().lower()
    h = int(hashlib.md5(normalized.encode("utf-8")).hexdigest(), 16)
    return day_of_week_it[h % len(day_of_week_it)]


def _schedule_matches_today(schedule: str, title: str) -> bool:
    """Return True if the RRULE *schedule* includes today.

    Parses the ``BYDAY`` component of an iCalendar RRULE string.  When
    ``BYDAY`` is absent the show is treated as *weekly* and a
    deterministic per-title day is assigned (identical logic to the old
    ``"weekly"`` sentinel).

    Examples::

        "FREQ=WEEKLY;BYDAY=WE,FR"  →  True on Wednesdays and Fridays
        "FREQ=WEEKLY"              →  True on the deterministic day for *title*
    """
    today = pd.Timestamp.now().strftime("%a").lower()[:3]
    byday_match = re.search(r"BYDAY=([A-Z,]+)", schedule)
    if byday_match:
        days: list[DAY_OF_WEEK] = [
            _RRULE_BYDAY[code]
            for code in byday_match.group(1).split(",")
            if code in _RRULE_BYDAY
        ]
        return today in days
    # No BYDAY → use deterministic weekly day
    return today == _get_deterministic_day(title)


def load_podcasts_config(include: list[str]) -> list[PodcastData]:
    """Load and schedule-filter podcast configurations.

    *include* is a list of config names or file paths passed to
    :func:`_load_config`.  Entries whose ``schedule`` RRULE does not
    match today are excluded.
    """
    configs: list[PodcastData] = []
    for target in include:
        configs.extend(_load_config(target))

    filtered: list[PodcastData] = []
    for it in configs:
        if it.schedule is not None and not _schedule_matches_today(
            it.schedule, it.title
        ):
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
