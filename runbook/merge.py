import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast

import dotenv
from pydantic import BaseModel

if TYPE_CHECKING:
    from src.models.pipeline import MergeResult

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


def _model_payloads(items: Sequence[BaseModel]) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in items]


def _feed_snapshot(
    kind: str,
    config_name: str,
    source_payloads: list[dict[str, object]],
    episode_payloads: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "kind": kind,
        "name": config_name,
        "source_count": len(source_payloads),
        "episode_count": len(episode_payloads),
        "sources": source_payloads,
        "episodes": episode_payloads,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _series_output_paths(output_root: Path, slug: str) -> dict[str, Path]:
    series_dir = output_root / slug
    feeds_dir = series_dir / "feeds"
    return {
        "series_dir": series_dir,
        "config": series_dir / "config.json",
        "references": feeds_dir / "references.json",
        "downloads": feeds_dir / "downloads.json",
        "combined": feeds_dir / "combined.json",
    }


def _write_series_outputs(
    output_root: Path,
    result: "MergeResult",
) -> dict[str, object]:
    config_payload = cast(dict[str, object], result.config.model_dump(mode="json"))
    slug = str(config_payload["slug"])
    paths = _series_output_paths(output_root, slug)

    reference_sources = cast(list[dict[str, object]], config_payload.get("references", []))
    download_sources = cast(list[dict[str, object]], config_payload.get("downloads", []))
    reference_payloads = _model_payloads(result.references)
    download_payloads = _model_payloads(result.downloads)
    merged_payloads = _model_payloads(result.episodes)

    _write_json(paths["config"], config_payload)
    _write_json(
        paths["references"],
        _feed_snapshot(
            "references",
            str(config_payload["name"]),
            reference_sources,
            reference_payloads,
        ),
    )
    _write_json(
        paths["downloads"],
        _feed_snapshot(
            "downloads",
            str(config_payload["name"]),
            download_sources,
            download_payloads,
        ),
    )
    _write_json(
        paths["combined"],
        {
            "kind": "combined",
            "name": config_payload["name"],
            "episode_count": len(merged_payloads),
            "episodes": merged_payloads,
        },
    )

    return {
        "name": config_payload["name"],
        "slug": slug,
        "directory": paths["series_dir"].relative_to(output_root).as_posix(),
        "config": paths["config"].relative_to(output_root).as_posix(),
        "feeds": {
            "references": paths["references"].relative_to(output_root).as_posix(),
            "downloads": paths["downloads"].relative_to(output_root).as_posix(),
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


def main() -> None:
    dotenv.load_dotenv()

    from src.app_common import load_podcasts_config
    from src.catalog import merge_config

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
        default=None,
        help=(
            "Write per-config output bundles under this directory, including config.json, "
            "feeds/references.json, feeds/downloads.json, feeds/combined.json, and top-level "
            "report.json/index.json."
        ),
    )
    args = parser.parse_args()

    configs = load_podcasts_config(
        include=args.include,
        skip_schedule_filter=args.skip_schedule_filter,
    )

    output: list[dict[str, object]] = []
    series_entries: list[dict[str, object]] = []
    for config in configs:
        result = merge_config(config)
        report = _build_series_report(config.name, args.include_counts, len(result.episodes))
        if args.include_counts:
            report["references_count"] = len(result.references)
            report["downloads_count"] = len(result.downloads)
        report["episodes"] = _model_payloads(result.episodes)
        output.append(report)
        if args.output_dir:
            output_root = Path(args.output_dir)
            series_entries.append(_write_series_outputs(output_root, result))

    if args.output_dir:
        _write_output_bundle(args.output_dir, output, series_entries)

    json.dump(output, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()