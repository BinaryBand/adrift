from __future__ import annotations

import json
import sys
from time import perf_counter
from typing import TYPE_CHECKING, Annotated

import typer

from adrift.cli import (
    IncludeConfigsOption,
    SkipScheduleFilterOption,
    TagsOption,
    bootstrap_run_configs,
    build_cli,
)
from adrift.services.merge import MergeUseCase
from adrift.utils.profiler import disable_profiling, enable_profiling, print_profile_report

if TYPE_CHECKING:
    from adrift.services.app_common import PodcastConfig
from adrift.services.merge_service import MergeRunOptions, MergeWriters
from adrift.services.merge_service import format_duration as _format_duration
from adrift.services.merge_service import write_json as service_write_json
from adrift.services.merge_service import write_output_bundle as service_write_output_bundle
from adrift.services.merge_service import write_report_file as service_write_report_file
from adrift.services.merge_service import write_series_outputs as service_write_series_outputs


def _write_json(path, payload: object) -> None:
    service_write_json(path, payload)


def _write_series_outputs(output_root, result) -> dict[str, object]:
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


def _run_merge(configs: list[PodcastConfig], options: MergeRunOptions):
    from adrift.utils.run_ui import create_run_ui

    writers = MergeWriters(
        write_json=_write_json,
        write_series_outputs=_write_series_outputs,
        write_output_bundle=_write_output_bundle,
        write_report_file=_write_report_file,
    )
    with create_run_ui(len(configs), "Matching") as ui, ui.output_context():
        return MergeUseCase(writers=writers).run(configs, options, ui)


def _build_stdout_output(merge_result, include_counts: bool) -> list[dict[str, object]]:
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


def _write_unmatched_references(merge_result, output_dir: str) -> None:
    try:
        from pathlib import Path

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
    except Exception as e:
        import sys

        sys.stderr.write(f"WARNING: _write_unmatched_references failed: {e}\n")


def _run(
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
    from contextlib import contextmanager, nullcontext

    @contextmanager
    def _maybe_profile():
        if profile:
            from pyinstrument import Profiler

            with Profiler() as p:
                yield
            with open(profile, "w") as f:
                f.write(p.output_html())
            sys.stderr.write(f"Profile written to {profile}\n")
        else:
            with nullcontext():
                yield

    if timings:
        enable_profiling()
    try:
        with _maybe_profile():
            load_start = perf_counter()
            configs, output_dir = bootstrap_run_configs(
                include, tags, skip_schedule_filter, output_dir
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
