from src.files.audio import _maybe_report_ffmpeg_progress


def test_maybe_report_ffmpeg_progress_reports_out_time_us() -> None:
    updates: list[tuple[int, int | None]] = []

    _maybe_report_ffmpeg_progress(
        "out_time_us=2500000\n",
        5,
        lambda current, total: updates.append((current, total)),
    )

    assert updates == [(2, 5)]


def test_maybe_report_ffmpeg_progress_ignores_unrelated_lines() -> None:
    updates: list[tuple[int, int | None]] = []

    _maybe_report_ffmpeg_progress(
        "progress=continue\n",
        5,
        lambda current, total: updates.append((current, total)),
    )

    assert updates == []
