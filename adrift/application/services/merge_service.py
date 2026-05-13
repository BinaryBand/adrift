from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

if TYPE_CHECKING:
    from adrift.models import MergeResult


JsonWriter = Callable[[Path, object], None]


@dataclass(frozen=True)
class MergeRunOptions:
    include_counts: bool = False
    pretty: bool = False
    output_dir: str = "downloads"
    output_file: str | None = None
    refresh_sources: bool = False
    timings_enabled: bool = False


def model_payloads(items: Sequence[BaseModel]) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in items]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def series_output_paths(output_root: Path, slug: str) -> dict[str, Path]:
    series_dir = output_root / slug
    feeds_dir = series_dir / "feeds"
    return {
        "series_dir": series_dir,
        "config": series_dir / "config.json",
        "combined": feeds_dir / "combined.json",
    }


def write_series_outputs(
    output_root: Path,
    result: "MergeResult",
    write_json_func: JsonWriter = write_json,
) -> dict[str, object]:
    config_payload = cast(dict[str, object], result.config.model_dump(mode="json"))
    slug = str(config_payload["slug"])
    paths = series_output_paths(output_root, slug)

    write_json_func(paths["config"], config_payload)
    combined_payload = cast(dict[str, object], result.model_dump(mode="json"))
    write_json_func(paths["combined"], combined_payload)

    return {
        "name": config_payload["name"],
        "slug": slug,
        "directory": paths["series_dir"].relative_to(output_root).as_posix(),
        "config": paths["config"].relative_to(output_root).as_posix(),
        "feeds": {
            "combined": paths["combined"].relative_to(output_root).as_posix(),
        },
    }


def write_output_bundle(
    output_dir: str,
    reports: list[dict[str, object]],
    series_entries: list[dict[str, object]],
    write_json_func: JsonWriter = write_json,
) -> None:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    write_json_func(output_root / "report.json", reports)
    write_json_func(
        output_root / "index.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "series": series_entries,
        },
    )


def write_report_file(
    output_file: str,
    reports: list[dict[str, object]],
    write_json_func: JsonWriter = write_json,
) -> None:
    write_json_func(Path(output_file), reports)


@dataclass(frozen=True)
class MergeWriters:
    write_json: JsonWriter = write_json
    write_series_outputs: Callable[[Path, "MergeResult"], dict[str, object]] = write_series_outputs
    write_output_bundle: Callable[[str, list[dict[str, object]], list[dict[str, object]]], None] = (
        write_output_bundle
    )
    write_report_file: Callable[[str, list[dict[str, object]]], None] = write_report_file


def format_duration(duration_seconds: float) -> str:
    return f"{duration_seconds * 1000:.1f}ms"


def emit_timings(config_name: str, timings: dict[str, float]) -> None:
    ordered_keys = [
        "process_feeds",
        "process_sources",
        "align_episodes",
        "merge_episodes",
        "write_outputs",
        "merge_config_total",
        "podcast_total",
    ]
    rendered_parts = [
        f"{key}={format_duration(timings[key])}" for key in ordered_keys if key in timings
    ]
    if rendered_parts:
        sys.stderr.write(f"TIMING {config_name}: {' '.join(rendered_parts)}\n")
