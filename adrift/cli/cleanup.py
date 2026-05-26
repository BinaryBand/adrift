"""Cleanup CLI: remove unmatched download audio files from S3."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from adrift.cli import (
    IncludeConfigsOption,
    SkipScheduleFilterOption,
    TagsOption,
    bootstrap_run_configs,
    build_cli,
)

_AUDIO_EXTENSIONS = frozenset({".mp3", ".opus"})


def _unmatched_indices(pairs: list[tuple[int, int]], total: int) -> list[int]:
    matched = {download_index for _, download_index in pairs}
    return [index for index in range(total) if index not in matched]


def _matched_download_slugs(result: Any) -> set[str]:
    from adrift.utils.title_normalization import normalize_title

    return {
        normalize_title(result.config.name, result.downloads[download_index].title)
        for _, download_index in result.pairs
    }


def _resolve_s3_key(s3: Any, bucket: str, prefix: str, slug: str) -> str | None:
    key_prefix = f"{prefix}/{slug}"
    actual_name = s3.exists(bucket, key_prefix)
    if actual_name is None:
        return None
    parent = Path(key_prefix).parent.as_posix()
    return f"{parent}/{actual_name}"


def _delete_key(s3: Any, bucket: str, key: str) -> None:
    s3.get_client().delete_object(Bucket=bucket, Key=key)
    s3.invalidate_file_map_cache(bucket, key)


def _audio_object_names(file_names: list[str]) -> list[str]:
    return [name for name in file_names if Path(name).suffix.lower() in _AUDIO_EXTENSIONS]


def _duplicate_audio_candidates(show: str, file_names: list[str]) -> list[str]:
    from adrift.utils.title_normalization import normalize_title

    by_canonical: dict[str, list[str]] = defaultdict(list)
    for name in _audio_object_names(file_names):
        canonical_name = f"{normalize_title(show, Path(name).stem)}.opus"
        by_canonical[canonical_name].append(name)

    duplicates: list[str] = []
    for canonical_name, names in by_canonical.items():
        if canonical_name not in names:
            continue
        duplicates.extend(name for name in names if name != canonical_name)
    return sorted(duplicates)


def _best_alignment_candidate_for_download(
    result: Any, download_index: int
) -> tuple[str, float, str] | None:
    best: tuple[str, float, str] | None = None
    references = getattr(result, "references", [])
    for trace in getattr(result, "match_traces", []):
        reference_index = getattr(trace, "reference_index", None)
        reference_title = f"<reference {reference_index}>"
        if isinstance(reference_index, int) and 0 <= reference_index < len(references):
            reference_title = references[reference_index].title
        for candidate in getattr(trace, "candidates", []):
            if getattr(candidate, "download_index", None) != download_index:
                continue
            reason = str(getattr(candidate, "reason", "unknown"))
            score = float(getattr(candidate, "score", 0.0))
            if best is None or score > best[1]:
                best = (reason, score, reference_title)
    return best


def _write_unmatched_verbose(result: Any, download_index: int) -> None:
    download = result.downloads[download_index]
    sys.stdout.write(f"    title:  {download.title}\n")
    sys.stdout.write(f"    source: {download.content}\n")
    best_candidate = _best_alignment_candidate_for_download(result, download_index)
    if best_candidate:
        reason, score, reference_title = best_candidate
        sys.stdout.write(f"    candidate ref: {reference_title!r}\n")
        sys.stdout.write(f"    alignment: reason={reason}, score={score:.2f}\n")
    else:
        sys.stdout.write("    alignment: no candidate trace for this download\n")


def _process_unmatched(
    result: Any,
    s3: Any,
    dry_run: bool,
    verbose: bool = False,
) -> tuple[int, int]:
    from adrift.services.download_client import s3_prefix
    from adrift.utils.title_normalization import normalize_title

    bucket, prefix = s3_prefix(result.config)
    indices = _unmatched_indices(result.pairs, len(result.downloads))
    matched_slugs = _matched_download_slugs(result)
    found = 0
    missing = 0
    for index in indices:
        download = result.downloads[index]
        slug = normalize_title(result.config.name, download.title)
        if slug in matched_slugs:
            continue
        key = _resolve_s3_key(s3, bucket, prefix, slug)
        if key is None:
            missing += 1
            continue
        label = "would delete" if dry_run else "deleted"
        sys.stdout.write(f"  {label}: {bucket}/{key}\n")
        if verbose:
            _write_unmatched_verbose(result, index)
        if not dry_run:
            _delete_key(s3, bucket, key)
        found += 1
    return found, missing


def _process_duplicate_audio_files(config: Any, s3: Any, dry_run: bool) -> int:
    from adrift.services.download_client import s3_prefix

    bucket, prefix = s3_prefix(config)
    duplicates = _duplicate_audio_candidates(config.name, s3.get_file_list(bucket, prefix, False))
    for name in duplicates:
        key = f"{prefix}/{name}"
        label = "would delete duplicate" if dry_run else "deleted duplicate"
        sys.stdout.write(f"  {label}: {bucket}/{key}\n")
        if not dry_run:
            _delete_key(s3, bucket, key)
    return len(duplicates)


def _run_cleanup(
    configs: list[Any],
    s3: Any,
    dry_run: bool,
    refresh_sources: bool,
    prune_duplicates: bool,
    verbose: bool = False,
) -> None:
    from adrift.services.catalog.merge import merge_config

    total_unmatched_found = 0
    total_missing = 0
    total_duplicates = 0
    for config in configs:
        result = merge_config(config, refresh_sources=refresh_sources)
        unmatched = _unmatched_indices(result.pairs, len(result.downloads))
        sys.stdout.write(f"\n{config.name}: {len(unmatched)} unmatched download(s)\n")
        if unmatched:
            found, missing = _process_unmatched(result, s3, dry_run, verbose=verbose)
            total_unmatched_found += found
            total_missing += missing
        if prune_duplicates:
            duplicate_count = _process_duplicate_audio_files(config, s3, dry_run)
            total_duplicates += duplicate_count
            if duplicate_count:
                sys.stdout.write(f"  duplicate object(s): {duplicate_count}\n")

    summary = "Would remove" if dry_run else "Removed"
    total_removed = total_unmatched_found + total_duplicates
    sys.stderr.write(
        f"\n{summary} {total_removed} file(s): {total_unmatched_found} unmatched, "
        f"{total_duplicates} duplicate. {total_missing} not found on S3.\n"
    )
    if dry_run and total_removed > 0:
        sys.stderr.write("Run with --no-dry-run to actually delete.\n")


def _run(
    include: IncludeConfigsOption = None,
    skip_schedule_filter: SkipScheduleFilterOption = False,
    tags: TagsOption = None,
    dry_run: Annotated[
        bool,
        typer.Option(help="List files that would be removed without deleting them."),
    ] = True,
    refresh_sources: Annotated[
        bool,
        typer.Option(help="Bypass fresh source caches and refetch source data."),
    ] = False,
    prune_duplicates: Annotated[
        bool,
        typer.Option(help="Remove duplicate audio objects when a canonical slug.opus exists."),
    ] = True,
    verbose: Annotated[
        bool,
        typer.Option(
            help=(
                "Show download title/source plus exact match-trace candidate reason and score "
                "for each deletion."
            )
        ),
    ] = False,
) -> None:
    from adrift.services.context import AppContext

    configs, _ = bootstrap_run_configs(include, tags, skip_schedule_filter)
    ctx = AppContext.from_env()
    _run_cleanup(
        configs,
        cast(Any, ctx.s3),
        dry_run,
        refresh_sources,
        prune_duplicates,
        verbose=verbose,
    )


app, main = build_cli(_run)


if __name__ == "__main__":
    main()
