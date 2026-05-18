from types import SimpleNamespace
from typing import Any, cast

from adrift.models import PodcastConfig
from tests.unit._fixtures import (
    _make_pipeline,
    _queue_item,
    make_build_download_queue_from_queue,
    make_capture_ui,
    make_ui_emit_only,
)


def test_download_episodes_skips_existing_and_counts_new_uploads() -> None:
    emitted: list[tuple[Any, str]] = []
    operations: list[str] = []
    ui = make_capture_ui(emitted, operations)
    config = cast(PodcastConfig, SimpleNamespace(name="CreepCast"))

    queue = [
        _queue_item(True, "Old 1"),
        _queue_item(True, "Old 2"),
        _queue_item(False, "New 1"),
        _queue_item(False, "New 2"),
        _queue_item(False, "New 3"),
    ]
    uploaded_titles: list[str] = []

    build_fn = make_build_download_queue_from_queue(queue)

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
        build_download_queue=build_fn,
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
    ui = make_ui_emit_only(emitted)
    config = cast(PodcastConfig, SimpleNamespace(name="CreepCast"))

    queue = [
        _queue_item(False, "Broken"),
        _queue_item(False, "Working"),
    ]

    build_fn = make_build_download_queue_from_queue(queue)

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
        build_download_queue=build_fn,
        download_and_upload=_download_and_upload,
    )._download_episodes([], config, downloaded_total=0)

    assert added == 1
    assert emitted == [("error", "CreepCast — Broken: boom")]


# Helpers `_queue_item` and `_make_pipeline` are provided by
# `tests.unit._fixtures` to avoid duplicating the same test scaffolding.
