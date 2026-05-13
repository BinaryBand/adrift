import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from runbook import (
    IncludeConfigsOption,
    SkipScheduleFilterOption,
    bootstrap_run_configs,
    make_main,
)
from src.catalog.alignment import _build_alignment_scores, _has_structured_number_mismatch
from src.catalog.merge import MergeConfigOptions, merge_config
from src.models import MergeResult, PodcastConfig, RssEpisode

DEFAULT_BORDERLINE_MIN = 0.60

_CSV_FIELDS = (
    "ref_id",
    "ref_title",
    "best_dl_id",
    "best_dl_title",
    "score",
    "category",
    "notes",
)


@dataclass(frozen=True)
class AuditRow:
    ref_id: str
    ref_title: str
    best_dl_id: str
    best_dl_title: str
    score: float
    category: str
    notes: str = ""


@dataclass(frozen=True)
class _AuditFrame:
    references: list[RssEpisode]
    downloads: list[RssEpisode]
    scores: dict[tuple[int, int], float]
    matched_pairs: set[tuple[int, int]]
    match_tolerance: float
    borderline_min: float


def _collect_merge_result(config: PodcastConfig, refresh_sources: bool) -> MergeResult:
    return merge_config(config, options=MergeConfigOptions(refresh_sources=refresh_sources))


def _best_candidate_by_reference(
    ref_count: int,
    scores: dict[tuple[int, int], float],
) -> dict[int, tuple[int, float]]:
    result: dict[int, tuple[int, float]] = {}
    for ref_idx in range(ref_count):
        candidates = [
            (dl_idx, score)
            for (candidate_ref_idx, dl_idx), score in scores.items()
            if candidate_ref_idx == ref_idx
        ]
        if candidates:
            result[ref_idx] = max(candidates, key=lambda it: it[1])
    return result


def _reused_download_indices(
    best_by_ref: dict[int, tuple[int, float]],
) -> set[int]:
    counts: dict[int, int] = {}
    for dl_idx, _score in best_by_ref.values():
        counts[dl_idx] = counts.get(dl_idx, 0) + 1
    return {dl_idx for dl_idx, count in counts.items() if count > 1}


def _render_score(score: float) -> str:
    return f"{score:.4f}"


def _classify_row(
    frame: _AuditFrame,
    ref_idx: int,
    best_idx: int,
    best_score: float,
    reused_indices: set[int],
) -> tuple[str, str]:
    ref = frame.references[ref_idx]
    dl = frame.downloads[best_idx]

    if _has_structured_number_mismatch(ref.title.lower(), dl.title.lower()):
        return "SERIES_MISMATCH", "Structured number mismatch"
    if best_idx in reused_indices:
        return "REUSED_TARGET", "Best download is preferred by multiple references"
    if best_score >= frame.match_tolerance and (ref_idx, best_idx) in frame.matched_pairs:
        return "MATCHED", "Selected by greedy matcher"
    if frame.borderline_min <= best_score < frame.match_tolerance:
        return "BORDERLINE", "Near match tolerance"
    return "UNCLEAR", "No clear alignment signal"


def _build_audit_rows(frame: _AuditFrame) -> list[AuditRow]:
    if not frame.downloads:
        return [
            AuditRow(
                ref_id=ref.id,
                ref_title=ref.title,
                best_dl_id="",
                best_dl_title="",
                score=0.0,
                category="NO_DOWNLOAD",
                notes="No download candidates",
            )
            for ref in frame.references
        ]

    best_by_ref = _best_candidate_by_reference(len(frame.references), frame.scores)
    reused_indices = _reused_download_indices(best_by_ref)

    rows: list[AuditRow] = []
    for ref_idx, ref in enumerate(frame.references):
        best = best_by_ref.get(ref_idx)
        if best is None:
            rows.append(
                AuditRow(
                    ref_id=ref.id,
                    ref_title=ref.title,
                    best_dl_id="",
                    best_dl_title="",
                    score=0.0,
                    category="UNCLEAR",
                    notes="No scored candidates",
                )
            )
            continue

        best_idx, best_score = best
        category, notes = _classify_row(
            frame,
            ref_idx,
            best_idx,
            best_score,
            reused_indices,
        )
        dl = frame.downloads[best_idx]
        rows.append(
            AuditRow(
                ref_id=ref.id,
                ref_title=ref.title,
                best_dl_id=dl.id,
                best_dl_title=dl.title,
                score=best_score,
                category=category,
                notes=notes,
            )
        )
    return rows


def _audit_rows_for_result(
    config: PodcastConfig,
    result: MergeResult,
    borderline_min: float,
) -> list[AuditRow]:
    scores = _build_alignment_scores(
        result.references,
        result.downloads,
        config.name,
        config.alignment,
    )
    return _build_audit_rows(
        _AuditFrame(
            references=result.references,
            downloads=result.downloads,
            scores=scores,
            matched_pairs=set(result.pairs),
            match_tolerance=config.alignment.match_tolerance,
            borderline_min=borderline_min,
        )
    )


def _audit_output_path(output_dir: str, slug: str) -> Path:
    return Path(output_dir) / slug / "alignment_audit.csv"


def _gold_audit_path(slug: str) -> Path:
    return Path("tests") / "resources" / "alignment" / f"{slug}_audit.csv"


def _gold_benchmark_path(slug: str) -> Path:
    return Path("tests") / "resources" / "alignment" / f"{slug}_benchmark.csv"


def _audit_row_as_dict(row: AuditRow) -> dict[str, str]:
    return {
        "ref_id": row.ref_id,
        "ref_title": row.ref_title,
        "best_dl_id": row.best_dl_id,
        "best_dl_title": row.best_dl_title,
        "score": _render_score(row.score),
        "category": row.category,
        "notes": row.notes,
    }


def _write_audit_csv(path: Path, rows: list[AuditRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_audit_row_as_dict(row))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [{k: (v or "") for k, v in row.items()} for row in reader]


def _audit_rows_as_dicts(rows: list[AuditRow]) -> list[dict[str, str]]:
    return [_audit_row_as_dict(row) for row in rows]


def _diff_summary(actual: list[dict[str, str]], expected: list[dict[str, str]]) -> str:
    if actual == expected:
        return ""
    preview = {
        "actual_count": len(actual),
        "expected_count": len(expected),
        "actual_preview": actual[:3],
        "expected_preview": expected[:3],
    }
    return json.dumps(preview, indent=2, ensure_ascii=True)


def _diff_against_gold(slug: str, rows: list[AuditRow]) -> tuple[bool, str]:
    expected = _read_csv_rows(_gold_audit_path(slug))
    actual = _audit_rows_as_dicts(rows)
    summary = _diff_summary(actual, expected)
    return (not summary, summary)


def _promotable_rows(rows: list[AuditRow]) -> list[tuple[str, str, str]]:
    promoted: list[tuple[str, str, str]] = []
    for row in rows:
        if not row.best_dl_title:
            continue
        if row.category == "MATCHED":
            promoted.append(("true", row.ref_title, row.best_dl_title))
        elif row.category == "SERIES_MISMATCH":
            promoted.append(("false", row.ref_title, row.best_dl_title))
    return promoted


def _promote_benchmark(slug: str, rows: list[AuditRow]) -> int:
    target = _gold_benchmark_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = {
        (row.get("label", ""), row.get("reference_title", ""), row.get("download_title", ""))
        for row in _read_csv_rows(target)
    }
    additions = [row for row in _promotable_rows(rows) if row not in existing]
    combined = sorted(
        existing | set(additions),
        key=lambda it: (it[1].lower(), it[2].lower(), it[0]),
    )

    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["label", "reference_title", "download_title"])
        writer.writeheader()
        for label, reference_title, download_title in combined:
            writer.writerow(
                {
                    "label": label,
                    "reference_title": reference_title,
                    "download_title": download_title,
                }
            )
    return len(additions)


def _run(
    include: IncludeConfigsOption = None,
    skip_schedule_filter: SkipScheduleFilterOption = False,
    tags: Annotated[
        list[str] | None,
        typer.Option(help="Tag(s) or podcast names to limit audits to"),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option(help="Output root for alignment_audit.csv files (default: downloads)."),
    ] = "",
    refresh_sources: Annotated[
        bool,
        typer.Option(help="Bypass fresh source caches and refetch source data."),
    ] = False,
    diff: Annotated[
        bool,
        typer.Option(
            help="Diff generated rows against tests/resources/alignment/<slug>_audit.csv."
        ),
    ] = False,
    promote: Annotated[
        bool,
        typer.Option(
            help=(
                "Promote confirmed audit rows into tests/resources/alignment/<slug>_benchmark.csv."
            )
        ),
    ] = False,
    borderline_min: Annotated[
        float,
        typer.Option(help="Lower bound for BORDERLINE classification (default: 0.60)."),
    ] = DEFAULT_BORDERLINE_MIN,
) -> None:
    configs, output_dir = bootstrap_run_configs(include, tags, skip_schedule_filter, output_dir)

    has_diff_failure = False
    for config in configs:
        result = _collect_merge_result(config, refresh_sources)
        rows = _audit_rows_for_result(config, result, borderline_min)
        output_path = _audit_output_path(output_dir, config.slug)
        _write_audit_csv(output_path, rows)
        typer.echo(f"wrote {output_path}")

        if diff:
            ok, summary = _diff_against_gold(config.slug, rows)
            if ok:
                typer.echo(f"diff ok for {config.slug}")
            else:
                has_diff_failure = True
                typer.echo(
                    f"diff mismatch for {config.slug} against {_gold_audit_path(config.slug)}"
                )
                typer.echo(summary)

        if promote:
            added = _promote_benchmark(config.slug, rows)
            typer.echo(f"promoted {added} benchmark rows to {_gold_benchmark_path(config.slug)}")

    if has_diff_failure:
        raise typer.Exit(code=1)


app = typer.Typer(add_completion=False)
app.command()(_run)

main = make_main(app)


if __name__ == "__main__":
    main()
