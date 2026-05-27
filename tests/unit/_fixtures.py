"""Shared test fixtures for unit tests under tests/unit.

Place small fake providers and helpers here to avoid repeating identical
test scaffolding across many test modules.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable

from adrift.models import (
    EpisodeData,
    FeedSource,
    MergeResult,
    PodcastConfig,
    RssEpisode,
)
from adrift.services.download import (
    DownloadPipeline,
    DownloadPipelineDeps,
    DownloadPipelineRuntime,
    DownloadRunOptions,
)


class _FakeProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def make_fake_ui(
    emit_cb: Callable[[Any, str], None] | None = None,
    set_operation_cb: Callable[[str], None] | None = None,
    clear_operation_cb: Callable[[], None] | None = None,
    operation_callback_cb: Callable[[int, int | None], None] | None = None,
) -> Any:
    """Return a lightweight fake UI object that delegates to callbacks.

    Callbacks are optional and may be simple lambdas that append to lists
    or no-op functions used in tests.
    """

    class _FakeUI:
        def emit(self, level: Any, message: str) -> None:
            if emit_cb:
                emit_cb(level, message)

        def set_operation(self, operation: str) -> None:
            if set_operation_cb:
                set_operation_cb(operation)

        def clear_operation(self) -> None:
            if clear_operation_cb:
                clear_operation_cb()

        def operation_callback(self, current: int, total: int | None) -> None:
            if operation_callback_cb:
                operation_callback_cb(current, total)

    return _FakeUI()


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
    options: DownloadRunOptions | None = None,
) -> DownloadPipeline:
    runtime = DownloadPipelineRuntime(
        ctx=ctx,
        ui=ui,
        options=options or DownloadRunOptions(max_downloads=max_downloads),
    )
    deps = DownloadPipelineDeps(
        merge_config=lambda config, options: None,
        merge_options_factory=lambda refresh, on_stage, callback: None,
        enrich_with_sponsors=lambda _merge_result: [],
        build_download_queue=build_download_queue,
        download_and_upload=download_and_upload,
        update_rss=lambda _config, _app_ctx: None,
        build_merge_callbacks=lambda _run_ui: (lambda _stage: None, lambda _current, _total: None),
        bot_detection_error=RuntimeError,
    )
    return DownloadPipeline(runtime, deps)


def _config(name: str = "Example Show", path: str = "/tmp/example-show") -> PodcastConfig:
    return PodcastConfig(
        name=name,
        path=path,
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="yt://@example-show")],
    )


def _rss_episode(identifier: str, title: str, content: str) -> RssEpisode:
    return RssEpisode(
        id=identifier,
        title=title,
        author="Example Author",
        content=content,
        description=f"Description for {title}",
        pub_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _merged_episode() -> EpisodeData:
    return EpisodeData(
        id="merged-1",
        title="Merged Episode",
        description="Merged description",
        source=["https://example.com/reference-1.mp3", "https://youtube.com/watch?v=abc123"],
        upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _make_merge_result(
    config: PodcastConfig,
    references: list[RssEpisode] | None = None,
    downloads: list[RssEpisode] | None = None,
    pairs: list[tuple[int, int]] | None = None,
    episodes: list[EpisodeData] | None = None,
) -> MergeResult:
    return MergeResult(
        config=config,
        references=references or [],
        downloads=downloads or [],
        pairs=pairs or [],
        episodes=episodes or [],
    )


def make_capture_ui(
    emitted: list[tuple[Any, str]], operations: list[str], clear_marker: str = "<cleared>"
) -> Any:
    """Return a UI that appends messages to `emitted` and operations to `operations`."""
    return make_fake_ui(
        emit_cb=lambda level, message: emitted.append((level, message)),
        set_operation_cb=lambda op: operations.append(op),
        clear_operation_cb=lambda: operations.append(clear_marker),
        operation_callback_cb=lambda current, total: None,
    )


def make_ui_emit_only(emitted: list[tuple[Any, str]]) -> Any:
    """Return a UI that only captures `emit` calls and no-ops the rest."""
    return make_fake_ui(
        emit_cb=lambda level, message: emitted.append((level, message)),
        set_operation_cb=lambda op: None,
        clear_operation_cb=lambda: None,
        operation_callback_cb=lambda current, total: None,
    )


def make_build_download_queue_from_queue(queue: list[Any]):
    """Return a builder function that ignores arguments and returns `queue`."""

    def _build_download_queue(episodes: Any, cfg: Any, ctx: Any) -> list[Any]:
        del episodes, cfg, ctx
        return queue

    return _build_download_queue


def sample_refs_downloads():
    """Return a standard (references, downloads, merged) triple used by tests."""
    return (
        [_rss_episode("ref-1", "Reference Episode", "https://example.com/reference-1.mp3")],
        [_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")],
        [_merged_episode()],
    )


def sample_merge_result(
    config: PodcastConfig, pairs: list[tuple[int, int]] | None = None
) -> MergeResult:
    refs, dls, merged = sample_refs_downloads()
    return _make_merge_result(
        config=config, references=refs, downloads=dls, pairs=pairs or [(0, 0)], episodes=merged
    )
