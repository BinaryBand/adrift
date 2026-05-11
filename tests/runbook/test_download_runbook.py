from types import SimpleNamespace
from typing import Any, cast

from src.application.download import (
    DownloadPipeline,
    DownloadPipelineDeps,
    DownloadPipelineRuntime,
    DownloadRunOptions,
)
from src.models import PodcastConfig


def test_download_episodes_skips_existing_and_counts_new_uploads() -> None:
    emitted: list[tuple[Any, str]] = []
    operations: list[str] = []

    def _ui_emit(level: Any, message: str) -> None:
        emitted.append((level, message))

    def _ui_set_operation(operation: str) -> None:
        operations.append(operation)

    def _ui_clear_operation() -> None:
        operations.append("<cleared>")

    def _ui_operation_callback(current: int, total: int | None) -> None:
        return None

    class _FakeUI:
        def emit(self, level: Any, message: str) -> None:
            _ui_emit(level, message)

        def set_operation(self, operation: str) -> None:
            _ui_set_operation(operation)

        def clear_operation(self) -> None:
            _ui_clear_operation()

        def operation_callback(self, current: int, total: int | None) -> None:
            _ui_operation_callback(current, total)

    ui = _FakeUI()
    config = cast(PodcastConfig, SimpleNamespace(name="CreepCast"))

    queue = [
        _queue_item(True, "Old 1"),
        _queue_item(True, "Old 2"),
        _queue_item(False, "New 1"),
        _queue_item(False, "New 2"),
        _queue_item(False, "New 3"),
    ]
    uploaded_titles: list[str] = []

    def _build_download_queue(episodes: Any, cfg: Any, ctx: Any) -> list[Any]:
        del episodes, cfg, ctx
        return queue

    def _download_and_upload(download_episode: Any, cfg: Any, ctx: Any) -> bool:
        del cfg
        assert ctx is not None
        ctx.event_bus.publish(
            SimpleNamespace(label=f"download audio: {download_episode.episode.title}")
        )
        uploaded_titles.append(download_episode.episode.title)
        return True

    class _EventBus:
        def publish(self, event: Any) -> None:
            if hasattr(event, "label"):
                operations.append(event.label)
            operations.append("<cleared>")

    ctx = SimpleNamespace(event_bus=_EventBus())

    added = _make_pipeline(
        ui=ui,
        ctx=ctx,
        max_downloads=2,
        build_download_queue=_build_download_queue,
        download_and_upload=_download_and_upload,
    )._download_episodes([], config, downloaded_total=0)

    assert added == 2
    assert uploaded_titles == ["New 1", "New 2"]
    assert emitted == []
    assert operations == [
        "download audio: New 1",
        "<cleared>",
        "download audio: New 2",
        "<cleared>",
    ]


def test_download_episodes_reports_nonfatal_errors_and_continues() -> None:
    emitted: list[tuple[Any, str]] = []

    def _ui_emit(level: Any, message: str) -> None:
        emitted.append((level, message))

    def _ui_set_operation(operation: str) -> None:
        return None

    def _ui_clear_operation() -> None:
        return None

    def _ui_operation_callback(current: int, total: int | None) -> None:
        return None

    class _FakeUI:
        def emit(self, level: Any, message: str) -> None:
            _ui_emit(level, message)

        def set_operation(self, operation: str) -> None:
            _ui_set_operation(operation)

        def clear_operation(self) -> None:
            _ui_clear_operation()

        def operation_callback(self, current: int, total: int | None) -> None:
            _ui_operation_callback(current, total)

    ui = _FakeUI()
    config = cast(PodcastConfig, SimpleNamespace(name="CreepCast"))

    queue = [
        _queue_item(False, "Broken"),
        _queue_item(False, "Working"),
    ]

    def _build_download_queue(episodes: Any, cfg: Any, ctx: Any) -> list[Any]:
        del episodes, cfg, ctx
        return queue

    def _download_and_upload(download_episode: Any, cfg: Any, ctx: Any) -> bool:
        del cfg
        assert ctx is not None
        if download_episode.episode.title == "Broken":
            raise ValueError("boom")
        return True

    ctx = SimpleNamespace(event_bus=SimpleNamespace(publish=lambda event: None))

    added = _make_pipeline(
        ui=ui,
        ctx=ctx,
        max_downloads=1,
        build_download_queue=_build_download_queue,
        download_and_upload=_download_and_upload,
    )._download_episodes([], config, downloaded_total=0)

    assert added == 1
    assert emitted == [("error", "CreepCast — Broken: boom")]


def _queue_item(exists_on_s3: bool, title: str) -> SimpleNamespace:
    return SimpleNamespace(
        exists_on_s3=exists_on_s3,
        episode=SimpleNamespace(episode=SimpleNamespace(title=title)),
    )


def _make_pipeline(
    *,
    ui: Any,
    ctx: Any,
    max_downloads: int,
    build_download_queue: Any,
    download_and_upload: Any,
) -> DownloadPipeline:
    runtime = DownloadPipelineRuntime(
        ctx=ctx,
        ui=ui,
        options=DownloadRunOptions(max_downloads=max_downloads),
    )
    deps = DownloadPipelineDeps(
        merge_config=lambda config, options: cast(Any, None),
        merge_options_factory=lambda refresh, on_stage, callback: cast(Any, None),
        enrich_with_sponsors=lambda _merge_result: cast(Any, []),
        build_download_queue=build_download_queue,
        download_and_upload=download_and_upload,
        update_rss=lambda _config, _app_ctx: None,
        build_merge_callbacks=lambda _run_ui: (
            lambda _stage: None,
            lambda _current, _total: None,
        ),
        bot_detection_error=RuntimeError,
    )
    return DownloadPipeline(runtime, deps)
