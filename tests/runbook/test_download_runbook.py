from types import SimpleNamespace

from runbook.download import _download_episodes


def test_download_episodes_skips_existing_and_counts_new_uploads() -> None:
    emitted: list[tuple[str, str]] = []
    operations: list[str] = []
    ui = SimpleNamespace(
        emit=lambda level, message: emitted.append((level, message)),
        set_operation=lambda operation: operations.append(operation),
        clear_operation=lambda: operations.append("<cleared>"),
        operation_callback=lambda current, total: None,
    )
    config = SimpleNamespace(name="CreepCast")

    queue = [
        _queue_item(True, "Old 1"),
        _queue_item(True, "Old 2"),
        _queue_item(False, "New 1"),
        _queue_item(False, "New 2"),
        _queue_item(False, "New 3"),
    ]
    uploaded_titles: list[str] = []

    def _build_download_queue(episodes, cfg):
        del episodes, cfg
        return queue

    def _download_and_upload(download_episode, cfg, progress_hooks):
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
    emitted: list[tuple[str, str]] = []
    ui = SimpleNamespace(
        emit=lambda level, message: emitted.append((level, message)),
        set_operation=lambda operation: None,
        clear_operation=lambda: None,
        operation_callback=lambda current, total: None,
    )
    config = SimpleNamespace(name="CreepCast")

    queue = [
        _queue_item(False, "Broken"),
        _queue_item(False, "Working"),
    ]

    def _build_download_queue(episodes, cfg):
        del episodes, cfg
        return queue

    def _download_and_upload(download_episode, cfg, progress_hooks):
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
