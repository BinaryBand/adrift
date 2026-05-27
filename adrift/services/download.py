"""Download pipeline use-case with explicit context and typed results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from adrift.models import DownloadEpisode, PodcastConfig
from adrift.models.errors import PipelineError
from adrift.models.stage_result import StageResult
from adrift.services.events import (
    DownloadCompleted,
    DownloadFailed,
    OperationStarted,
    ProgressUpdated,
)
from adrift.utils.title_normalization import normalize_title

if TYPE_CHECKING:
    from adrift.models import MergeResult
    from adrift.services.catalog.merge import MergeConfigOptions
    from adrift.services.context import AppContext
    from adrift.services.download_process import DownloadQueueItem
    from adrift.utils.progress import Callback
    from adrift.utils.run_ui import BaseRunUI

BuildQueueFn = Callable[
    [list[DownloadEpisode], PodcastConfig, "AppContext"],
    list["DownloadQueueItem"],
]

_DOWNLOAD_OPERATION_ERRORS = (OSError, RuntimeError, ValueError)


@dataclass(frozen=True)
class DownloadRunOptions:
    skip_download: bool = False
    skip_update: bool = False
    max_downloads: int = 10
    refresh_sources: bool = False
    show_download_plan: bool = False


@dataclass(frozen=True)
class _MergeCallbacks:
    on_stage: Callable[[str], None]
    progress: Callback


@dataclass(frozen=True)
class DownloadPipelineRuntime:
    ctx: AppContext
    ui: BaseRunUI
    options: DownloadRunOptions


@dataclass(frozen=True)
class DownloadPipelineDeps:
    merge_config: Callable[[PodcastConfig, MergeConfigOptions], MergeResult]
    merge_options_factory: Callable[[bool, Callable[[str], None], Callback], MergeConfigOptions]
    enrich_with_sponsors: Callable[[MergeResult], list[DownloadEpisode]]
    build_download_queue: BuildQueueFn
    download_and_upload: Callable[[DownloadEpisode, PodcastConfig, AppContext], bool]
    update_rss: Callable[[PodcastConfig, AppContext], None]
    build_merge_callbacks: Callable[[BaseRunUI], tuple[Callable[[str], None], Callback]]
    bot_detection_error: type[BaseException]


class DownloadPipeline:
    """Application pipeline for merge -> enrich -> download -> RSS update."""

    def __init__(self, runtime: DownloadPipelineRuntime, deps: DownloadPipelineDeps) -> None:
        self._runtime = runtime
        self._deps = deps
        self._events_subscribed = False

    def run(self, configs: list[PodcastConfig]) -> StageResult[int]:
        self._subscribe_download_events()
        on_stage, progress = self._deps.build_merge_callbacks(self._runtime.ui)
        callbacks = _MergeCallbacks(on_stage=on_stage, progress=progress)
        downloaded_total = 0
        errors: list[PipelineError] = []

        for config in configs:
            try:
                downloaded_total += self._run_single_config(config, callbacks, downloaded_total)
            except self._deps.bot_detection_error:
                raise
            except _DOWNLOAD_OPERATION_ERRORS as exc:
                errors.append(
                    PipelineError(
                        label="download",
                        message=f"{config.name}: {exc}",
                        fatal=False,
                        cause=exc,
                    )
                )
                self._runtime.ui.emit("error", f"{config.name} — pipeline failed: {exc}")
                self._runtime.ui.advance()

        return StageResult(value=downloaded_total, errors=tuple(errors))

    def _run_single_config(
        self,
        config: PodcastConfig,
        callbacks: _MergeCallbacks,
        downloaded_total: int,
    ) -> int:
        self._runtime.ui.set_podcast(config.name)
        episodes = self._merge_and_enrich(config, callbacks)

        added = 0
        if self._runtime.options.skip_download:
            if self._runtime.options.show_download_plan:
                self._runtime.ui.set_stage("download")
                added = self._plan_downloads(episodes, config, downloaded_total)
        else:
            self._runtime.ui.set_stage("download")
            added = self._download_episodes(episodes, config, downloaded_total)

        if not self._runtime.options.skip_update:
            self._runtime.ui.set_stage("rss")
            self._deps.update_rss(config, self._runtime.ctx)

        self._runtime.ui.set_stage("done")
        self._runtime.ui.advance()
        return added

    def _plan_downloads(
        self,
        episodes: list[DownloadEpisode],
        config: PodcastConfig,
        downloaded_total: int,
    ) -> int:
        planned = 0
        for queue_item in self._deps.build_download_queue(episodes, config, self._runtime.ctx):
            if downloaded_total + planned >= self._runtime.options.max_downloads:
                break
            if queue_item.exists_on_s3:
                continue
            title = queue_item.episode.episode.title
            slug = normalize_title(config.name, title)
            self._runtime.ui.emit("info", f"would download: {config.path}/{slug}.opus")
            planned += 1
        return planned

    def _merge_and_enrich(
        self,
        config: PodcastConfig,
        callbacks: _MergeCallbacks,
    ) -> list[DownloadEpisode]:
        self._runtime.ui.set_stage("merge")
        merge_options = self._deps.merge_options_factory(
            self._runtime.options.refresh_sources,
            callbacks.on_stage,
            callbacks.progress,
        )
        result = self._deps.merge_config(config, merge_options)
        self._runtime.ui.set_stage("enrich")
        return self._deps.enrich_with_sponsors(result)

    def _download_episodes(
        self,
        episodes: list[DownloadEpisode],
        config: PodcastConfig,
        downloaded_total: int,
    ) -> int:
        additional_downloads = 0
        for queue_item in self._deps.build_download_queue(episodes, config, self._runtime.ctx):
            if downloaded_total + additional_downloads >= self._runtime.options.max_downloads:
                break
            if queue_item.exists_on_s3:
                continue
            try:
                newly_uploaded = self._deps.download_and_upload(
                    queue_item.episode,
                    config,
                    self._runtime.ctx,
                )
                if newly_uploaded:
                    additional_downloads += 1
            except self._deps.bot_detection_error:
                raise
            except _DOWNLOAD_OPERATION_ERRORS as exc:
                self._runtime.ui.clear_operation()
                self._runtime.ui.emit(
                    "error",
                    f"{config.name} — {queue_item.episode.episode.title}: {exc}",
                )
        return additional_downloads

    def _subscribe_download_events(self) -> None:
        if self._events_subscribed:
            return
        self._runtime.ctx.event_bus.subscribe(
            OperationStarted,
            lambda event: self._runtime.ui.set_operation(event.label),
        )
        self._runtime.ctx.event_bus.subscribe(
            ProgressUpdated,
            lambda event: self._runtime.ui.operation_callback(event.current, event.total),
        )
        self._runtime.ctx.event_bus.subscribe(
            DownloadCompleted,
            lambda _event: self._runtime.ui.clear_operation(),
        )
        self._runtime.ctx.event_bus.subscribe(
            DownloadFailed,
            lambda _event: self._runtime.ui.clear_operation(),
        )
        self._events_subscribed = True


__all__ = [
    "DownloadRunOptions",
    "DownloadPipelineRuntime",
    "DownloadPipelineDeps",
    "DownloadPipeline",
]
