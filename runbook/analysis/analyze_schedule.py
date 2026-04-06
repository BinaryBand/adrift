#!/usr/bin/env python
"""Analyze publish cadence for download sources (YouTube or feed URLs)."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import feedparser
import requests
import tomllib
from dateutil import parser as date_parser
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "youtube.toml"
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


@dataclass(frozen=True)
class Target:
    source: str
    label: str
    kind: str
    filter_regex: str | None


@dataclass(frozen=True)
class Sample:
    video_id: str
    title: str
    published_utc: datetime


@dataclass(frozen=True)
class Analysis:
    target: Target
    feed_url: str
    fetched_count: int
    dated_count: int
    filtered_count: int
    analyzed: list[Sample]


@dataclass(frozen=True)
class RunContext:
    total: int
    limit: int
    tz: ZoneInfo


def _is_direct_feed(raw: str) -> bool:
    value = raw.strip().lower()
    return value.startswith(("http://", "https://")) and "feeds/videos.xml" in value


def _is_youtube_target(raw: str) -> bool:
    value = raw.strip().lower()
    if value.startswith(("yt://", "@")):
        return True
    if _is_direct_feed(value):
        return False
    return "youtube.com" in value or "youtu.be" in value


def _normalize_youtube_shorthand(raw: str) -> str:
    value = raw.strip()
    if value.startswith("yt://@"):
        return f"https://www.youtube.com/@{value.removeprefix('yt://@')}/videos"
    if value.startswith("@"):
        return f"https://www.youtube.com/{value}/videos"
    if value.startswith("yt://"):
        suffix = value.removeprefix("yt://").lstrip("/")
        return f"https://www.youtube.com/{suffix}"
    return value


def _is_youtube_netloc(netloc: str) -> bool:
    return "youtube.com" in netloc or "youtu.be" in netloc


def _is_short_youtube_netloc(netloc: str) -> bool:
    return "youtu.be" in netloc


def _normalize_youtube_path(path: str) -> str:
    trimmed = path.rstrip("/")
    if trimmed.startswith("/@") and not trimmed.endswith("/videos"):
        return trimmed + "/videos"
    return trimmed


def _normalize_youtube_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    netloc = parsed.netloc.lower()
    if not _is_youtube_netloc(netloc):
        return raw.strip()
    if _is_short_youtube_netloc(netloc):
        return raw.strip()

    path = _normalize_youtube_path(parsed.path)
    return urlunparse(("https", "www.youtube.com", path, "", "", ""))


def _normalize_youtube_target(raw: str) -> str:
    return _normalize_youtube_url(_normalize_youtube_shorthand(raw))


def _normalize_feed_target(raw: str) -> str:
    parsed = urlparse(raw.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, "")
    )


def _target_key(raw: str) -> tuple[str, str]:
    if _is_youtube_target(raw):
        return ("youtube", _normalize_youtube_target(raw).rstrip("/").lower())
    return ("feed", _normalize_feed_target(raw))


def _exclude_lookahead(pattern: str) -> str:
    return f"(?!{pattern[1:]})" if pattern.startswith("^") else f"(?!.*{pattern})"


def _include_lookahead(patterns: list[str]) -> str | None:
    return f"(?=.*(?:{'|'.join(patterns)}))" if patterns else None


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def _has_filter_patterns(include: list[str], exclude: list[str]) -> bool:
    return bool(include or exclude)


def _filter_parts(include: list[str], exclude: list[str]) -> list[str]:
    parts: list[str] = ["(?i)^"]
    parts.extend(_exclude_lookahead(pattern) for pattern in exclude)
    include_part = _include_lookahead(include)
    if include_part:
        parts.append(include_part)
    parts.append(".*$")
    return parts


def _filters_to_regex(filters: Any) -> str | None:
    if not isinstance(filters, dict):
        return None
    include = _string_list(filters.get("include"))
    exclude = _string_list(filters.get("exclude"))
    if not _has_filter_patterns(include, exclude):
        return None
    return "".join(_filter_parts(include, exclude))


def _build_target(name: str, idx: int, source: dict[str, Any]) -> Target | None:
    url = source.get("url")
    if not isinstance(url, str):
        return None
    kind = "youtube" if _is_youtube_target(url) else "feed"
    return Target(
        source=url,
        label=f"{name} downloads[{idx}]",
        kind=kind,
        filter_regex=_filters_to_regex(source.get("filters", {})),
    )


def _podcast_downloads(podcast: Any) -> list[dict[str, Any]]:
    if not isinstance(podcast, dict):
        return []
    downloads = podcast.get("downloads", [])
    if not isinstance(downloads, list):
        return []
    return [source for source in downloads if isinstance(source, dict)]


def _targets_from_podcast(podcast: Any) -> list[Target]:
    if not isinstance(podcast, dict):
        return []
    name = str(podcast.get("name", "Unknown"))
    targets: list[Target] = []
    for idx, source in enumerate(_podcast_downloads(podcast), start=1):
        if target := _build_target(name, idx, source):
            targets.append(target)
    return targets


def _load_download_targets() -> list[Target]:
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    targets: list[Target] = []
    for podcast in data.get("podcasts", []):
        targets.extend(_targets_from_podcast(podcast))
    return targets


def _arg_target(target_arg: str) -> Target:
    return Target(
        source=target_arg,
        label="arg",
        kind="youtube" if _is_youtube_target(target_arg) else "feed",
        filter_regex=None,
    )


def _targets_for_arg(target_arg: str | None) -> list[Target]:
    configured = _load_download_targets()
    if target_arg is None:
        return configured
    key = _target_key(target_arg)
    matched = [target for target in configured if _target_key(target.source) == key]
    return matched or [_arg_target(target_arg)]


def _resolve_channel_id(channel_url: str) -> str:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": 0,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False) or {}
    channel_id = info.get("channel_id") or info.get("id")
    if isinstance(channel_id, str) and channel_id.startswith("UC"):
        return channel_id
    raise ValueError(f"Could not resolve channel_id from {channel_url}")


def _youtube_feed_url(source: str) -> str:
    normalized = _normalize_youtube_target(source)
    channel_id = _resolve_channel_id(normalized)
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _feed_url_for_target(target: Target) -> str:
    return (
        target.source.strip()
        if target.kind == "feed"
        else _youtube_feed_url(target.source)
    )


def _fetch_feed(feed_url: str) -> feedparser.FeedParserDict:
    response = requests.get(feed_url, timeout=20)
    response.raise_for_status()
    return feedparser.parse(response.text)


def _parse_datetime_value(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = date_parser.parse(str(raw))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_datetime_tuple(raw: Any) -> datetime | None:
    if not isinstance(raw, tuple) or len(raw) < 6:
        return None
    try:
        return datetime(*raw[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def _entry_field(entry: feedparser.FeedParserDict, name: str) -> Any:
    return getattr(entry, name, None) or entry.get(name)


def _first_named_datetime(
    entry: feedparser.FeedParserDict, names: tuple[str, ...]
) -> datetime | None:
    for name in names:
        if dt := _parse_datetime_value(_entry_field(entry, name)):
            return dt
    return None


def _first_named_datetime_tuple(
    entry: feedparser.FeedParserDict, names: tuple[str, ...]
) -> datetime | None:
    for name in names:
        if dt := _parse_datetime_tuple(_entry_field(entry, name)):
            return dt
    return None


def _parse_entry_datetime(entry: feedparser.FeedParserDict) -> datetime | None:
    dt = _first_named_datetime(entry, ("published", "updated", "pubDate"))
    if dt is not None:
        return dt
    return _first_named_datetime_tuple(
        entry, ("published_parsed", "updated_parsed", "pubDate_parsed")
    )


def _entry_raw_id(entry: feedparser.FeedParserDict) -> str:
    return str(_entry_field(entry, "id") or "")


def _video_id_from_raw_id(raw_id: str) -> str:
    return raw_id.split(":")[-1] if raw_id.startswith("yt:video:") else raw_id


def _entry_video_id(entry: feedparser.FeedParserDict) -> str:
    yid = _entry_field(entry, "yt_videoid")
    if isinstance(yid, str) and yid:
        return yid
    return _video_id_from_raw_id(_entry_raw_id(entry))


def _sample_from_entry(entry: feedparser.FeedParserDict) -> Sample | None:
    dt = _parse_entry_datetime(entry)
    if dt is None:
        return None
    return Sample(
        video_id=_entry_video_id(entry),
        title=str(getattr(entry, "title", "") or entry.get("title", "")),
        published_utc=dt,
    )


def _extract_samples(feed: feedparser.FeedParserDict) -> list[Sample]:
    samples = [
        sample for entry in feed.entries if (sample := _sample_from_entry(entry))
    ]
    samples.sort(key=lambda sample: sample.published_utc, reverse=True)
    return samples


def _apply_filter(samples: list[Sample], filter_regex: str | None) -> list[Sample]:
    if not filter_regex:
        return samples
    compiled = re.compile(filter_regex)
    return [sample for sample in samples if compiled.search(sample.title)]


def _weekday_counts(samples: list[Sample], tz: ZoneInfo) -> Counter[str]:
    counts: Counter[str] = Counter()
    for sample in samples:
        day = WEEKDAYS[sample.published_utc.astimezone(tz).weekday()]
        counts[day] += 1
    return counts


def _ordered_days(day_counts: Counter[str]) -> list[str]:
    return [day for day, _ in day_counts.most_common()]


def _top_day(day_counts: Counter[str]) -> tuple[str, int]:
    return day_counts.most_common(1)[0]


def _single_day_suggestion(day_counts: Counter[str], total: int) -> list[str] | None:
    top_day, top_count = _top_day(day_counts)
    if top_count / total >= 0.70:
        return [top_day]
    return None


def _two_day_suggestion(
    day_counts: Counter[str], ordered: list[str], total: int
) -> list[str] | None:
    if len(ordered) < 2:
        return None
    top_day, top_count = _top_day(day_counts)
    second_day = ordered[1]
    if (top_count + day_counts[second_day]) / total >= 0.80:
        return [top_day, second_day]
    return None


def _suggest_bydays(day_counts: Counter[str], total: int) -> list[str]:
    ordered = _ordered_days(day_counts)
    if not ordered or total <= 0:
        return []
    if single_day := _single_day_suggestion(day_counts, total):
        return single_day
    if two_day := _two_day_suggestion(day_counts, ordered, total):
        return two_day
    return ordered[:3]


def _analyzed_samples(samples: list[Sample], limit: int) -> list[Sample]:
    return samples[:limit]


def _build_analysis(target: Target, limit: int) -> Analysis:
    feed_url = _feed_url_for_target(target)
    feed = _fetch_feed(feed_url)
    dated = _extract_samples(feed)
    filtered = _apply_filter(dated, target.filter_regex)
    analyzed = _analyzed_samples(filtered, limit)
    if not analyzed:
        raise ValueError("No entries remain after filter/timestamp parsing")
    return Analysis(
        target, feed_url, len(feed.entries), len(dated), len(filtered), analyzed
    )


def _print_weekday_distribution(samples: list[Sample], tz: ZoneInfo) -> None:
    day_counts = _weekday_counts(samples, tz)
    print("Weekday distribution:")
    for day in WEEKDAYS:
        count = day_counts.get(day, 0)
        pct = (count / len(samples)) * 100 if samples else 0.0
        print(f"  {day}: {count:3d} ({pct:5.1f}%)")


def _print_recent_samples(samples: list[Sample], tz: ZoneInfo) -> None:
    print("Recent samples:")
    for sample in samples[:8]:
        local = sample.published_utc.astimezone(tz).isoformat()
        title = sample.title[:90] + ("..." if len(sample.title) > 90 else "")
        print(f"  {local} | {sample.video_id} | {title}")


def _print_suggested_values(samples: list[Sample], tz: ZoneInfo) -> None:
    day_counts = _weekday_counts(samples, tz)
    bydays = _suggest_bydays(day_counts, len(samples))
    print("Suggested TOML values:")
    if bydays:
        joined = ",".join(bydays)
        print(f'  schedule = ["FREQ=WEEKLY;BYDAY={joined}"]')
        print(f'  r_rules = ["FREQ=WEEKLY;BYDAY={joined}"]')
        return
    print("  schedule = []")
    print("  r_rules = []")


def _print_result(analysis: Analysis, tz: ZoneInfo) -> None:
    print(f"Source: {analysis.target.source}")
    print(f"Config label: {analysis.target.label}")
    print(f"Kind: {analysis.target.kind}")
    print(f"Feed URL: {analysis.feed_url}")
    print(
        "Counts: "
        f"fetched={analysis.fetched_count} dated={analysis.dated_count} "
        f"filtered={analysis.filtered_count} analyzed={len(analysis.analyzed)}"
    )
    print(f"Active filter: {analysis.target.filter_regex or '(none)'}")
    _print_weekday_distribution(analysis.analyzed, tz)
    _print_recent_samples(analysis.analyzed, tz)
    _print_suggested_values(analysis.analyzed, tz)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze schedule cadence for YouTube/download feed sources"
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="yt:// source, @handle, YouTube URL, or direct feed URL",
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Max filtered entries to analyze"
    )
    parser.add_argument("--tz", default="UTC", help="IANA timezone for grouping output")
    return parser.parse_args()


def _validate_limit(limit: int) -> bool:
    if limit >= 1:
        return True
    print("--limit must be >= 1")
    return False


def _load_runtime_targets(target_arg: str | None) -> list[Target]:
    targets = _targets_for_arg(target_arg)
    if targets:
        return targets
    print("No downloads targets found in config/youtube.toml")
    return []


def _print_separator(idx: int, total: int) -> None:
    if idx < total:
        print("\n" + "-" * 72 + "\n")


def _run_target(idx: int, target: Target, context: RunContext) -> bool:
    try:
        analysis = _build_analysis(target, context.limit)
        print(f"[{idx}/{context.total}]")
        _print_result(analysis, context.tz)
        return False
    except Exception as exc:
        print(f"[{idx}/{context.total}] ERROR: {target.source}: {exc}")
        return True


def _run_targets(targets: list[Target], limit: int, tz: ZoneInfo) -> int:
    failures = 0
    context = RunContext(total=len(targets), limit=limit, tz=tz)
    for idx, target in enumerate(targets, start=1):
        failures += int(_run_target(idx, target, context))
        _print_separator(idx, context.total)
    return failures


def main() -> int:
    args = parse_args()
    if not _validate_limit(args.limit):
        return 1

    tz = ZoneInfo(args.tz)
    targets = _load_runtime_targets(args.target)
    if not targets:
        return 1
    return 1 if _run_targets(targets, args.limit, tz) else 0


if __name__ == "__main__":
    raise SystemExit(main())
