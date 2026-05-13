import json
import sys
from time import perf_counter
from typing import Annotated

import dotenv
import typer

from runbook import normalize_cli_inputs
from src.application.merge import MergeUseCase
from src.application.services.merge_service import (
    MergeRunOptions,
    MergeWriters,
)
from src.application.services.merge_service import (
    format_duration as _format_duration,
)
from src.application.services.merge_service import (
    write_json as service_write_json,
)
from src.application.services.merge_service import (
    write_output_bundle as service_write_output_bundle,
)
from src.application.services.merge_service import (
    write_report_file as service_write_report_file,
)
from src.application.services.merge_service import (
    write_series_outputs as service_write_series_outputs,
)


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


def _load_configs(
    include: list[str],
    skip_schedule_filter: bool,
    tags: list[str],
    timings: bool,
) -> list[object]:
    from src.app_common import filter_podcasts_by_tags, load_podcasts_config

    load_start = perf_counter()
    configs = load_podcasts_config(
        include=include,
        skip_schedule_filter=skip_schedule_filter,
    )
    load_duration = perf_counter() - load_start
    if timings:
        sys.stderr.write(f"TIMING load_configs: {_format_duration(load_duration)}\n")
    return filter_podcasts_by_tags(configs, tags)


def _build_run_options(
    include_counts: bool,
    pretty: bool,
    output_dir: str,
    output_file: str | None,
    refresh_sources: bool,
    timings: bool,
) -> MergeRunOptions:
    return MergeRunOptions(
        include_counts=include_counts,
        pretty=pretty,
        output_dir=output_dir,
        output_file=output_file,
        refresh_sources=refresh_sources,
        timings_enabled=timings,
    )


def _run_merge(configs: list[object], options: MergeRunOptions):
    from src.utils.run_ui import create_run_ui

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
            "episodes": [episode.model_dump(mode="json") for episode in merged.episodes],
        }
        for merged in merge_result.value
    ]


def _run(
    include: Annotated[
        list[str] | None,
        typer.Option(help="Config files to include"),
    ] = None,
    skip_schedule_filter: Annotated[
        bool,
        typer.Option(help="Include podcast configs even when their schedule does not match today."),
    ] = False,
    tags: Annotated[
        list[str] | None,
        typer.Option(help="Tag(s) or podcast names to limit merges to"),
    ] = None,
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
        typer.Option(
            help=(
                "Write per-config output bundles under this directory (defaults to downloads/), "
                "including config.json, feeds/combined.json, and top-level report.json/index.json."
            )
        ),
    ] = "",
    output_file: Annotated[
        str | None,
        typer.Option(
            help="Write the cumulative JSON report to this file after each processed podcast."
        ),
    ] = None,
    refresh_sources: Annotated[
        bool,
        typer.Option(help="Bypass fresh source caches and refetch source data."),
    ] = False,
    timings: Annotated[
        bool,
        typer.Option(help="Emit per-podcast stage timings to stderr."),
    ] = False,
) -> None:
    dotenv.load_dotenv()
    include, tags, output_dir = normalize_cli_inputs(include, tags, output_dir)
    configs = _load_configs(include, skip_schedule_filter, tags, timings)
    options = _build_run_options(
        include_counts,
        pretty,
        output_dir,
        output_file,
        refresh_sources,
        timings,
    )
    merge_result = _run_merge(configs, options)
    output = _build_stdout_output(merge_result, include_counts)
    json.dump(output, sys.stdout, indent=2 if pretty else None)
    sys.stdout.write("\n")


app = typer.Typer(add_completion=False)
app.command()(_run)


def main() -> None:
    app(standalone_mode=False)


if __name__ == "__main__":
    main()
