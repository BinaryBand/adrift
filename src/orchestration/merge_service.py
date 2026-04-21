from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from src import catalog
from src.models.podcast_config import PodcastConfig

if TYPE_CHECKING:
    from src.models.pipeline import MergeResult
    from src.utils.run_ui import BaseRunUI


JsonWriter = Callable[[Path, object], None]


@dataclass(frozen=True)
class MergeRunOptions:
    include_counts: bool = False
    pretty: bool = False
    output_dir: str = "downloads"
    output_file: str | None = None
    refresh_sources: bool = False
    timings_enabled: bool = False
    skip_sankey: bool = False
    skip_report: bool = False
    sankey_format: str = "sankey"


def build_series_report(
    config_name: str,
    include_counts: bool,
    merged_count: int,
) -> dict[str, object]:
    report: dict[str, object] = {
        "name": config_name,
        "merged_count": merged_count,
    }
    if include_counts:
        report["references_count"] = 0
        report["downloads_count"] = 0
    return report


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


@dataclass
class MergeOutputState:
    reports: list[dict[str, object]]
    series_entries: list[dict[str, object]]


@dataclass(frozen=True)
class MergeExecutionContext:
    options: MergeRunOptions
    ui: "BaseRunUI"
    writers: MergeWriters


@dataclass(frozen=True)
class MergeCallbacks:
    on_stage: Callable[[str], None]
    progress: Callable[[int, int | None], None]


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


def _build_merge_report(result: "MergeResult", include_counts: bool) -> dict[str, object]:
    report = build_series_report(result.config.name, include_counts, len(result.episodes))
    if include_counts:
        report["references_count"] = len(result.references)
        report["downloads_count"] = len(result.downloads)
    report["episodes"] = model_payloads(result.episodes)
    return report


def _run_merge(
    config: "PodcastConfig",
    context: MergeExecutionContext,
    callbacks: MergeCallbacks,
    timings: dict[str, float],
) -> "MergeResult":
    return catalog.merge_config(
        config,
        refresh_sources=context.options.refresh_sources,
        timings=timings if context.options.timings_enabled else None,
        on_stage=callbacks.on_stage,
        callback=callbacks.progress,
    )


def _write_bundle_for_result(
    result: "MergeResult",
    output_dir: str,
    state: MergeOutputState,
    writers: MergeWriters,
) -> Path:
    output_root = Path(output_dir)
    state.series_entries.append(writers.write_series_outputs(output_root, result))
    writers.write_output_bundle(output_dir, state.reports, state.series_entries)
    return output_root


def _maybe_write_output_file(
    output_file: str | None,
    reports: list[dict[str, object]],
    writers: MergeWriters,
) -> None:
    if output_file:
        writers.write_report_file(output_file, reports)


def _record_timings(
    config_name: str,
    podcast_start: float,
    write_start: float,
    timings: dict[str, float],
) -> None:
    timings["write_outputs"] = perf_counter() - write_start
    timings["podcast_total"] = perf_counter() - podcast_start
    emit_timings(config_name, timings)


def _run_single_config(
    config: "PodcastConfig",
    context: MergeExecutionContext,
    state: MergeOutputState,
    callbacks: MergeCallbacks,
) -> None:
    context.ui.set_podcast(config.name)
    timings: dict[str, float] = {}
    podcast_start = perf_counter()
    result = _run_merge(config, context, callbacks, timings)
    context.ui.set_stage("done")
    state.reports.append(_build_merge_report(result, context.options.include_counts))

    write_start = perf_counter()
    write_merge_outputs(result, context, state)
    if context.options.timings_enabled:
        _record_timings(config.name, podcast_start, write_start, timings)
    context.ui.advance()


def merge_configs(
    configs: list["PodcastConfig"],
    options: MergeRunOptions,
    ui: "BaseRunUI",
    *,
    writers: MergeWriters | None = None,
) -> list[dict[str, object]]:
    from src.utils.run_ui import build_merge_callbacks

    context = MergeExecutionContext(options=options, ui=ui, writers=writers or MergeWriters())
    state = MergeOutputState(reports=[], series_entries=[])
    on_stage, callback = build_merge_callbacks(ui)
    callbacks = MergeCallbacks(on_stage=on_stage, progress=callback)
    for config in configs:
        _run_single_config(config, context, state, callbacks)

    return state.reports


def write_merge_outputs(
    result: "MergeResult",
    context: MergeExecutionContext,
    state: MergeOutputState,
) -> None:
    if context.options.output_dir:
        output_root = _write_bundle_for_result(
            result,
            context.options.output_dir,
            state,
            context.writers,
        )
        write_optional_outputs(result, context, output_root)
    _maybe_write_output_file(context.options.output_file, state.reports, context.writers)


def write_optional_outputs(
    result: "MergeResult",
    context: MergeExecutionContext,
    output_root: Path,
) -> None:
    _maybe_generate_mermaid(result, context, output_root)
    _maybe_generate_report(result, context, output_root)


def _maybe_generate_mermaid(
    result: "MergeResult",
    context: MergeExecutionContext,
    output_root: Path,
) -> None:
    if context.options.skip_sankey:
        return
    try:
        from src.adapters import get_mermaid_adapter
        from src.ports.mermaid import MermaidRenderOptions

        adapter = get_mermaid_adapter()
        adapter.generate_diagrams(
            result,
            output_root,
            MermaidRenderOptions(
                format=context.options.sankey_format,
                overwrite=True,
            ),
        )
    except Exception as exc:  # pragma: no cover - non-fatal optional feature
        context.ui.emit("warning", f"MERMAID generation failed for {result.config.name}: {exc}")


def _maybe_generate_report(
    result: "MergeResult",
    context: MergeExecutionContext,
    output_root: Path,
) -> None:
    if context.options.skip_report:
        return
    try:
        from src.adapters import get_report_adapter

        adapter = get_report_adapter()
        adapter.generate_reports(result, output_root)
    except Exception as exc:  # pragma: no cover - non-fatal optional feature
        context.ui.emit("warning", f"REPORT generation failed for {result.config.name}: {exc}")
