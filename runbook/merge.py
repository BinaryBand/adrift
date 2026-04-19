import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, cast

import dotenv
from pydantic import BaseModel

if TYPE_CHECKING:
    from src.models.pipeline import MergeResult

DF_TARGETS = ["config/*.toml"]
DEFAULT_OUTPUT_DIR = "downloads"


def _build_series_report(
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


def _model_payloads(items: Sequence[BaseModel]) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in items]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _series_output_paths(output_root: Path, slug: str) -> dict[str, Path]:
    series_dir = output_root / slug
    feeds_dir = series_dir / "feeds"
    return {
        "series_dir": series_dir,
        "config": series_dir / "config.json",
        "combined": feeds_dir / "combined.json",
    }


def _write_series_outputs(
    output_root: Path,
    result: "MergeResult",
) -> dict[str, object]:
    config_payload = cast(dict[str, object], result.config.model_dump(mode="json"))
    slug = str(config_payload["slug"])
    paths = _series_output_paths(output_root, slug)

    # Previous implementation produced separate per-feed snapshots. The
    # current behavior writes the full `MergeResult` into the combined file
    # so we no longer need the individual source/episode payload variables.

    _write_json(paths["config"], config_payload)
    # Write the full MergeResult payload into the per-series combined file.
    # This replaces the previous separate references/downloads/combined files
    # with a single per-podcast file containing the complete `MergeResult`.
    combined_payload = cast(dict[str, object], result.model_dump(mode="json"))
    _write_json(paths["combined"], combined_payload)

    return {
        "name": config_payload["name"],
        "slug": slug,
        "directory": paths["series_dir"].relative_to(output_root).as_posix(),
        "config": paths["config"].relative_to(output_root).as_posix(),
        "feeds": {
            "combined": paths["combined"].relative_to(output_root).as_posix(),
        },
    }


def _write_output_bundle(
    output_dir: str,
    reports: list[dict[str, object]],
    series_entries: list[dict[str, object]],
) -> None:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "report.json", reports)
    _write_json(
        output_root / "index.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "series": series_entries,
        },
    )


def _write_report_file(output_file: str, reports: list[dict[str, object]]) -> None:
    _write_json(Path(output_file), reports)


def _format_duration(duration_seconds: float) -> str:
    return f"{duration_seconds * 1000:.1f}ms"


def _emit_timings(config_name: str, timings: dict[str, float]) -> None:
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
        f"{key}={_format_duration(timings[key])}" for key in ordered_keys if key in timings
    ]
    if rendered_parts:
        sys.stderr.write(f"TIMING {config_name}: {' '.join(rendered_parts)}\n")


def main() -> None:
    dotenv.load_dotenv()

    from src.app_common import load_podcasts_config
    from src.catalog import merge_config
    from src.utils.run_ui import build_merge_callbacks, create_run_ui

    parser = argparse.ArgumentParser(
        description="Fetch source episodes and produce merged alignment output."
    )
    parser.add_argument("--include", nargs="*", default=DF_TARGETS, help="Config files to include")
    parser.add_argument(
        "--skip-schedule-filter",
        action="store_true",
        default=False,
        help="Include podcast configs even when their schedule does not match today.",
    )
    parser.add_argument(
        "--include-counts",
        action="store_true",
        default=False,
        help="Include reference/download counts in the JSON report.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=False,
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Write per-config output bundles under this directory (defaults to downloads/), "
            "including config.json, "
            "feeds/combined.json, and top-level "
            "report.json/index.json."
        ),
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Write the cumulative JSON report to this file after each processed podcast.",
    )
    parser.add_argument(
        "--refresh-sources",
        action="store_true",
        default=False,
        help="Bypass fresh source caches and refetch source data.",
    )
    parser.add_argument(
        "--timings",
        action="store_true",
        default=False,
        help="Emit per-podcast stage timings to stderr.",
    )
    parser.add_argument(
        "--skip-sankey",
        action="store_true",
        default=False,
        help="Skip generating Mermaid sankey diagrams (enabled by default).",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        default=False,
        help="Skip generating the per-podcast markdown report (enabled by default).",
    )
    parser.add_argument(
        "--sankey-format",
        choices=["sankey", "flowchart"],
        default="sankey",
        help="Mermaid diagram format to generate (sankey or flowchart).",
    )
    args = parser.parse_args()

    load_start = perf_counter()
    configs = load_podcasts_config(
        include=args.include,
        skip_schedule_filter=args.skip_schedule_filter,
    )
    load_duration = perf_counter() - load_start
    if args.timings:
        sys.stderr.write(f"TIMING load_configs: {_format_duration(load_duration)}\n")

    output: list[dict[str, object]] = []
    series_entries: list[dict[str, object]] = []
    with create_run_ui(len(configs), "Matching") as ui, ui.output_context():
        on_stage, callback = build_merge_callbacks(ui)
        for config in configs:
            ui.set_podcast(config.name)
            timings: dict[str, float] = {}
            podcast_start = perf_counter()
            result = merge_config(
                config,
                refresh_sources=args.refresh_sources,
                timings=timings if args.timings else None,
                on_stage=on_stage,
                callback=callback,
            )
            ui.set_stage("done")
            report = _build_series_report(config.name, args.include_counts, len(result.episodes))
            if args.include_counts:
                report["references_count"] = len(result.references)
                report["downloads_count"] = len(result.downloads)
            report["episodes"] = _model_payloads(result.episodes)
            output.append(report)

            write_start = perf_counter()
            if args.output_dir:
                output_root = Path(args.output_dir)
                series_entries.append(_write_series_outputs(output_root, result))
                _write_output_bundle(args.output_dir, output, series_entries)
                if not args.skip_sankey:
                    try:
                        from src.adapters import get_mermaid_adapter
                        from src.ports.mermaid import MermaidRenderOptions

                        adapter = get_mermaid_adapter()
                        adapter.generate_diagrams(
                            result,
                            output_root,
                            MermaidRenderOptions(
                                format=args.sankey_format,
                                overwrite=True,
                            ),
                        )
                    except Exception as exc:  # pragma: no cover - non-fatal optional feature
                        ui.emit("warning", f"MERMAID generation failed for {config.name}: {exc}")
                if not args.skip_report:
                    try:
                        from src.adapters import get_report_adapter

                        adapter = get_report_adapter()
                        adapter.generate_reports(result, output_root)
                    except Exception as exc:  # pragma: no cover - non-fatal optional feature
                        ui.emit("warning", f"REPORT generation failed for {config.name}: {exc}")
            if args.output_file:
                _write_report_file(args.output_file, output)
            if args.timings:
                timings["write_outputs"] = perf_counter() - write_start
                timings["podcast_total"] = perf_counter() - podcast_start
                _emit_timings(config.name, timings)
            ui.advance()

    json.dump(output, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
