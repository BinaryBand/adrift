from types import SimpleNamespace
from typing import Any, cast

from runbook.download import _download_episodes
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

    def _build_download_queue(episodes: Any, cfg: Any) -> list[Any]:
        del episodes, cfg
        return queue

    def _download_and_upload(download_episode: Any, cfg: Any, progress_hooks: Any) -> bool:
        del cfg
        assert progress_hooks is not None
        if progress_hooks.on_operation is not None:
            progress_hooks.on_operation(f"download audio: {download_episode.episode.title}")
        uploaded_titles.append(download_episode.episode.title)
        if progress_hooks.on_complete is not None:
            progress_hooks.on_complete()
        return True

    added = _download_episodes(
        [],
        config,
        downloaded_total=0,
        max_downloads=2,
        ui=ui,
        build_download_queue=_build_download_queue,
        download_and_upload=_download_and_upload,
        bot_detection_error=RuntimeError,
    )

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

    def _build_download_queue(episodes: Any, cfg: Any) -> list[Any]:
        del episodes, cfg
        return queue

    def _download_and_upload(download_episode: Any, cfg: Any, progress_hooks: Any) -> bool:
        del cfg
        assert progress_hooks is not None
        if download_episode.episode.title == "Broken":
            raise ValueError("boom")
        return True

    added = _download_episodes(
        [],
        config,
        downloaded_total=0,
        max_downloads=1,
        ui=ui,
        build_download_queue=_build_download_queue,
        download_and_upload=_download_and_upload,
        bot_detection_error=RuntimeError,
    )

    assert added == 1
    assert emitted == [("error", "CreepCast — Broken: boom")]


def _queue_item(exists_on_s3: bool, title: str) -> SimpleNamespace:
    return SimpleNamespace(
        exists_on_s3=exists_on_s3,
        episode=SimpleNamespace(episode=SimpleNamespace(title=title)),
    )
