import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

import dotenv

from src.application.merge import MergeUseCase
from src.models import PodcastConfig

if TYPE_CHECKING:
    from src.models import MergeResult

from src.orchestration.merge_service import (
    MergeRunOptions,
    MergeWriters,
)
from src.orchestration.merge_service import (
    format_duration as _format_duration,
)
from src.orchestration.merge_service import (
    write_json as service_write_json,
)
from src.orchestration.merge_service import (
    write_output_bundle as service_write_output_bundle,
)
from src.orchestration.merge_service import (
    write_report_file as service_write_report_file,
)
from src.orchestration.merge_service import (
    write_series_outputs as service_write_series_outputs,
)

DF_TARGETS = ["config/*.toml"]
DEFAULT_OUTPUT_DIR = "downloads"


def _write_json(path: Path, payload: object) -> None:
    service_write_json(path, payload)


def _write_series_outputs(output_root: Path, result: "MergeResult") -> dict[str, object]:
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


def main() -> None:
    dotenv.load_dotenv()

    from src.app_common import load_podcasts_config
    from src.utils.run_ui import create_run_ui

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
        "--tags",
        nargs="*",
        default=[],
        help="Tag(s) or podcast names to limit merges to",
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

    # Filter configs by tags/podcast names when requested (same behaviour as runbook/download.py)
    if args.tags:
        normalized_tags = [t.strip().lower() for t in args.tags if t.strip()]

        def _matches_tag(cfg: PodcastConfig) -> bool:
            if cfg.name.lower() in normalized_tags:
                return True
            if cfg.slug.lower() in normalized_tags:
                return True
            for tg in getattr(cfg, "tags", []):
                if tg.lower() in normalized_tags:
                    return True
            return False

        configs = [c for c in configs if _matches_tag(c)]

    options = MergeRunOptions(
        include_counts=args.include_counts,
        pretty=args.pretty,
        output_dir=args.output_dir,
        output_file=args.output_file,
        refresh_sources=args.refresh_sources,
        timings_enabled=args.timings,
        skip_sankey=args.skip_sankey,
        skip_report=args.skip_report,
        sankey_format=args.sankey_format,
    )
    writers = MergeWriters(
        write_json=_write_json,
        write_series_outputs=_write_series_outputs,
        write_output_bundle=_write_output_bundle,
        write_report_file=_write_report_file,
    )
    with create_run_ui(len(configs), "Matching") as ui, ui.output_context():
        merge_result = MergeUseCase(writers=writers).run(configs, options, ui)

    output = [
        {
            "name": merged.config.name,
            "merged_count": len(merged.episodes),
            **(
                {
                    "references_count": len(merged.references),
                    "downloads_count": len(merged.downloads),
                }
                if args.include_counts
                else {}
            ),
            "episodes": [episode.model_dump(mode="json") for episode in merged.episodes],
        }
        for merged in merge_result.value
    ]

    json.dump(output, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
