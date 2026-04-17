import argparse
import json
import sys

import dotenv

DF_TARGETS = ["config/*.toml"]


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


def main() -> None:
    dotenv.load_dotenv()

    from src.app_common import load_podcasts_config
    from src.catalog import merge_config, process_feeds, process_sources

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
    args = parser.parse_args()

    configs = load_podcasts_config(
        include=args.include,
        skip_schedule_filter=args.skip_schedule_filter,
    )

    output: list[dict[str, object]] = []
    for config in configs:
        merged = merge_config(config)
        report = _build_series_report(config.name, args.include_counts, len(merged))
        if args.include_counts:
            report["references_count"] = len(process_feeds(config))
            report["downloads_count"] = len(process_sources(config))
        report["episodes"] = [episode.model_dump(mode="json") for episode in merged]
        output.append(report)

    json.dump(output, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()