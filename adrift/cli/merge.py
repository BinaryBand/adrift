"""Merge CLI: align podcast references with downloads and produce output bundles."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, Any

import typer

from adrift.cli import (
    IncludeConfigsOption,
    SkipScheduleFilterOption,
    TagsOption,
    bootstrap_run_configs,
    build_cli,
)
from adrift.core.services.merge import MergeUseCase
from adrift.core.util.profiler import disable_profiling, enable_profiling, print_profile_report

if TYPE_CHECKING:
    from collections.abc import Iterator

    from adrift.core.services.app_common import PodcastConfig
from adrift.core.services.merge_service import MergeRunOptions, MergeWriters
from adrift.core.services.merge_service import format_duration as _format_duration
from adrift.core.services.merge_service import write_json as service_write_json
from adrift.core.services.merge_service import write_output_bundle as service_write_output_bundle
from adrift.core.services.merge_service import write_report_file as service_write_report_file
from adrift.core.services.merge_service import write_series_outputs as service_write_series_outputs


def _write_json(path: Path, payload: object) -> None:
    service_write_json(path, payload)


def _write_series_outputs(output_root: Path, result: Any) -> dict[str, object]:  # noqa: ANN401
    return service_write_series_outputs(output_root, result, write_json_func=_write_json)


def _write_output_bundle(
    output_dir: str,
    reports: list[dict[str, object]],
    series_entries: list[dict[str, object]],
) -> None:
    service_write_output_bundle(
        output_dir,
        reports,
        series_entries,
        write_json_func=_write_json,
    )


def _write_report_file(output_file: str, reports: list[dict[str, object]]) -> None:
    service_write_report_file(output_file, reports, write_json_func=_write_json)


def _run_merge(configs: list[PodcastConfig], options: MergeRunOptions) -> Any:  # noqa: ANN401
    from adrift.core.util.run_ui import create_run_ui  # noqa: PLC0415

    writers = MergeWriters(
        write_json=_write_json,
        write_series_outputs=_write_series_outputs,
        write_output_bundle=_write_output_bundle,
        write_report_file=_write_report_file,
    )
    with create_run_ui(len(configs), "Matching") as ui, ui.output_context():
        return MergeUseCase(writers=writers).run(configs, options, ui)


def _build_stdout_output(merge_result: Any, include_counts: bool) -> list[dict[str, object]]:  # noqa: ANN401
    return [
        {
            "name": merged.config.name,
            "merged_count": len(merged.episodes),
            **(
                {
                    "references_count": len(merged.references),
                    "downloads_count": len(merged.downloads),
                }
                if include_counts
                else {}
            ),
            "episodes": [
                episode.model_dump(mode="json", exclude={"description"})
                for episode in merged.episodes
            ],
        }
        for merged in merge_result.value
    ]


def _write_unmatched_references(merge_result: Any, output_dir: str) -> None:  # noqa: ANN401
    try:
        unmatched_per_series: list[dict[str, object]] = []
        for merged in merge_result.value:
            unmatched_refs: list[dict[str, object]] = []
            for trace in merged.match_traces:
                if trace.matched_download_index is None:
                    ref = merged.references[trace.reference_index]
                    unmatched_refs.append(ref.model_dump(mode="json"))
            if unmatched_refs:
                cfg = merged.config.model_dump(mode="json")
                unmatched_per_series.append(
                    {
                        "name": cfg.get("name"),
                        "slug": str(cfg.get("slug")),
                        "unmatched_references": unmatched_refs,
                    }
                )
        if unmatched_per_series:
            outpath = Path(output_dir) / "unmatched_references.json"
            _write_json(outpath, unmatched_per_series)
    except (OSError, ValueError) as e:
        sys.stderr.write(f"WARNING: _write_unmatched_references failed: {e}\n")


def _run(  # noqa: PLR0913
    include: IncludeConfigsOption = None,
    skip_schedule_filter: SkipScheduleFilterOption = False,
    tags: TagsOption = None,
    include_counts: Annotated[
        bool,
        typer.Option(help="Include reference/download counts in the JSON report."),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option(help="Pretty-print JSON output."),
    ] = False,
    output_dir: Annotated[
        str,
        typer.Option(help="Root directory for output bundles (default: downloads/)."),
    ] = "",
    output_file: Annotated[
        str | None,
        typer.Option(help="Write the cumulative JSON report to this file."),
    ] = None,
    refresh_sources: Annotated[
        bool,
        typer.Option(help="Bypass fresh source caches and refetch source data."),
    ] = False,
    timings: Annotated[
        bool,
        typer.Option(help="Emit per-podcast stage timings to stderr."),
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option(help="Write a pyinstrument HTML call-tree profile to this file."),
    ] = None,
) -> None:
    from contextlib import contextmanager, nullcontext  # noqa: PLC0415

    @contextmanager
    def _maybe_profile() -> Iterator[None]:
        if profile:
            from pyinstrument import Profiler  # noqa: PLC0415

            with Profiler() as p:
                yield
            with Path(profile).open("w") as f:
                f.write(p.output_html())
            sys.stderr.write(f"Profile written to {profile}\n")
        else:
            with nullcontext():
                yield

    from adrift.adapters import (  # noqa: PLC0415
        get_alignment_backend_provider,
        get_episode_source_factory,
    )
    from adrift.adapters.process.alignment import ensure_rust_alignment_backend  # noqa: PLC0415

    ensure_rust_alignment_backend()

    if timings:
        enable_profiling()
    try:
        with _maybe_profile():
            load_start = perf_counter()
            configs, output_dir = bootstrap_run_configs(
                include, tags, skip_schedule_filter=skip_schedule_filter, output_dir=output_dir
            )
            load_duration = perf_counter() - load_start
            if timings:
                sys.stderr.write(f"TIMING load_configs: {_format_duration(load_duration)}\n")
            options = MergeRunOptions(
                include_counts=include_counts,
                pretty=pretty,
                output_dir=output_dir,
                output_file=output_file,
                refresh_sources=refresh_sources,
                timings_enabled=timings,
                episode_source_factory=get_episode_source_factory(),
                alignment_provider=get_alignment_backend_provider(),
            )
            merge_result = _run_merge(configs, options)
            _write_unmatched_references(merge_result, output_dir)
            output = _build_stdout_output(merge_result, include_counts)
            json.dump(output, sys.stdout, indent=2 if pretty else None)
            sys.stdout.write("\n")
    finally:
        if timings:
            print_profile_report()
            disable_profiling()


app, main = build_cli(_run)


if __name__ == "__main__":
    main()
