"""Merge use-case for orchestrating config merges with typed results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from adrift.core.models.errors import PipelineError
from adrift.core.models.stage_result import StageResult
from adrift.core.services import catalog
from adrift.core.services.merge_service import (
    MergeRunOptions,
    MergeWriters,
    emit_timings,
    model_payloads,
)
from adrift.core.util.profiler import profile
from adrift.core.util.run_ui import build_merge_callbacks

if TYPE_CHECKING:
    from collections.abc import Callable

    from adrift.core.models import MergeResult, PodcastConfig
    from adrift.core.util.run_ui import BaseRunUI


_MERGE_OPERATION_ERRORS = (OSError, RuntimeError, ValueError)


@dataclass
class _MergeUseCaseState:
    reports: list[dict[str, object]] = field(default_factory=list)
    series_entries: list[dict[str, object]] = field(default_factory=list)
    results: list[MergeResult] = field(default_factory=list)


@dataclass(frozen=True)
class _MergeCallbacks:
    on_stage: Callable[[str], None]
    progress: Callable[[int, int | None], None]


@dataclass
class _MergeRuntime:
    options: MergeRunOptions
    ui: BaseRunUI
    state: _MergeUseCaseState
    errors: list[PipelineError]


@dataclass
class _MergeConfigFrame:
    config: PodcastConfig
    callbacks: _MergeCallbacks
    runtime: _MergeRuntime
    timings: dict[str, float]
    podcast_start: float


class MergeUseCase:
    """Application-level merge orchestration with StageResult error accumulation."""

    def __init__(self, writers: MergeWriters | None = None) -> None:
        """Store the injectable output writers (defaults to ``MergeWriters()``)."""
        self._writers = writers or MergeWriters()

    @profile
    def run(
        self,
        configs: list[PodcastConfig],
        options: MergeRunOptions,
        ui: BaseRunUI,
    ) -> StageResult[list[MergeResult]]:
        """Merge each config, write outputs, and return accumulated results."""
        state = _MergeUseCaseState()
        on_stage, callback = build_merge_callbacks(ui)
        errors: list[PipelineError] = []
        callbacks = _MergeCallbacks(on_stage=on_stage, progress=callback)
        runtime = _MergeRuntime(options=options, ui=ui, state=state, errors=errors)

        for config in configs:
            self._run_single_config(
                _MergeConfigFrame(
                    config=config,
                    callbacks=callbacks,
                    runtime=runtime,
                    timings={},
                    podcast_start=0.0,
                )
            )

        return StageResult(value=state.results, errors=tuple(errors))

    @profile
    def _run_single_config(self, frame: _MergeConfigFrame) -> None:
        frame.runtime.ui.set_podcast(frame.config.name)
        frame.podcast_start = perf_counter()
        result = self._attempt_merge(frame)
        if result is None:
            frame.runtime.ui.advance()
            return

        self._record_success(result, frame)
        frame.runtime.ui.advance()

    def _attempt_merge(self, frame: _MergeConfigFrame) -> MergeResult | None:
        try:
            return catalog.merge_config(
                frame.config,
                refresh_sources=frame.runtime.options.refresh_sources,
                timings=frame.timings if frame.runtime.options.timings_enabled else None,
                on_stage=frame.callbacks.on_stage,
                callback=frame.callbacks.progress,
                episode_source_factory=frame.runtime.options.episode_source_factory,
                alignment_provider=frame.runtime.options.alignment_provider,
            )
        except _MERGE_OPERATION_ERRORS as exc:
            frame.runtime.errors.append(
                PipelineError(
                    label="merge",
                    message=f"{frame.config.name}: {exc}",
                    fatal=True,
                    cause=exc,
                )
            )
            frame.runtime.ui.emit("error", f"{frame.config.name} — merge failed: {exc}")
            return None

    def _record_success(self, result: MergeResult, frame: _MergeConfigFrame) -> None:
        frame.runtime.ui.set_stage("done")
        frame.runtime.state.results.append(result)
        frame.runtime.state.reports.append(
            self._build_report(result, include_counts=frame.runtime.options.include_counts)
        )

        write_start = perf_counter()
        self._write_outputs(result, frame.runtime.options, frame.runtime.state)

        if frame.runtime.options.timings_enabled:
            frame.timings["write_outputs"] = perf_counter() - write_start
            frame.timings["podcast_total"] = perf_counter() - frame.podcast_start
            emit_timings(frame.config.name, frame.timings)

    @staticmethod
    def _build_report(result: MergeResult, *, include_counts: bool) -> dict[str, object]:
        report: dict[str, object] = {
            "name": result.config.name,
            "merged_count": len(result.episodes),
            "episodes": model_payloads(result.episodes),
        }
        if include_counts:
            report["references_count"] = len(result.references)
            report["downloads_count"] = len(result.downloads)
        return report

    @profile
    def _write_outputs(
        self,
        result: MergeResult,
        options: MergeRunOptions,
        state: _MergeUseCaseState,
    ) -> None:
        if options.output_dir:
            output_root = Path(options.output_dir)
            state.series_entries.append(self._writers.write_series_outputs(output_root, result))
            self._writers.write_output_bundle(
                options.output_dir,
                state.reports,
                state.series_entries,
            )

        if options.output_file:
            self._writers.write_report_file(options.output_file, state.reports)


__all__ = ["MergeUseCase"]
